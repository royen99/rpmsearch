from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import zlib
import lzma
import time
import xml.etree.ElementTree as ET
import httpx
import ssl
import certifi
from pathlib import Path
import os
import json
import re

app = FastAPI()

@app.middleware("http")
async def add_root_path(request: Request, call_next):
    prefix = request.headers.get("x-forwarded-prefix", "")
    request.scope["root_path"] = prefix.rstrip("/")
    response = await call_next(request)
    return response

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

REPO_BASE_URL = os.getenv("REPO_BASE_URL", "http://default-repo-base-url.example.com")
RELEASE_API_URL = os.getenv("RELEASE_API_URL", "http://default-releases-api.example.com")

AVAILABLE_REPOS = [
    "rhel-7-server-els-rpms",
    "rhel-8-for-x86_64-baseos-rpms", 
    "rhel-8-for-x86_64-appstream-rpms",
    "rhel-9-for-x86_64-baseos-rpms",
    "rhel-9-for-x86_64-appstream-rpms",
    "rhel-10-for-x86_64-baseos-beta-rpms",
    "rhel-10-for-x86_64-appstream-beta-rpms",
    "rhel-7-epel-rpms",
    "rhel-8-epel-rpms",
    "rhel-9-epel-rpms",
    "codeready-builder-for-rhel-8-x86_64-rpms",
    "codeready-builder-for-rhel-9-x86_64-rpms",
    "codeready-builder-beta-for-rhel-10-x86_64-rpms"
]

def create_ssl_context():
    ssl_context = ssl.create_default_context()
    ssl_context.load_verify_locations(cafile=certifi.where())
    return ssl_context

async def fetch_releases():
    try:
        ssl_context = create_ssl_context()
        async with httpx.AsyncClient(verify=ssl_context) as client:
            response = await client.get(
                RELEASE_API_URL,
                timeout=5.0
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract just the repodata-tags
            return data.get("repodata-tags", {})
            
    except httpx.HTTPStatusError as e:
        print(f"HTTP error fetching releases: {e}")
    except httpx.RequestError as e:
        print(f"Request error fetching releases: {e}")
    except Exception as e:
        print(f"Unexpected error fetching releases: {e}")
    return {} 

@app.get("/", response_class=HTMLResponse)
async def query_form(request: Request):
    versions = await fetch_releases()
    return templates.TemplateResponse("query.html", {
        "request": request,
        "repos": AVAILABLE_REPOS,
        "versions": versions
    })

@app.get("/api/search")
async def search_packages(
    package: str = Query(..., min_length=2),
    repo: str = Query(None),
    version: str = Query(None),
    exact_match: bool = Query(False)
):
    results = []
    repos_to_search = [repo] if repo else AVAILABLE_REPOS
    
    for repo_name in repos_to_search:
        packages = await get_repo_packages(repo_name, version)
        
        if exact_match:
            if package.lower() in packages:
                results.append({
                    "repo": repo_name,
                    "package": packages[package.lower()],
                    "version_tag": version
                })
        else:
            # Partial match - search all packages containing the query
            matching_packages = [
                {"name": name, **data}
                for name, data in packages.items()
                if package.lower() in name
            ]
            if matching_packages:
                results.append({
                    "repo": repo_name,
                    "matches": matching_packages,
                    "version_tag": version,
                    "match_count": len(matching_packages)
                })
            
    return {
        "query": package,
        "exact_match": exact_match,
        "results": results
    }

async def get_repo_packages(repo_name: str, version_tag: str = None):
    """Final version with correct path resolution for primary metadata"""
    cache_file = Path(f"/tmp/query_cache/{version_tag or 'latest'}_{repo_name}.json")
    
    try:
        # Use cached data if fresh
        if cache_file.exists() and (time.time() - cache_file.stat().st_mtime < 7200):
            with open(cache_file) as f:
                return json.load(f)
    
        # Build base URL
        base_path = f"{REPO_BASE_URL}/{version_tag}" if version_tag else REPO_BASE_URL
        repomd_url = f"{base_path}/{repo_name}/repodata/repomd.xml"
        print(f"Processing repository: {repomd_url}")

        async with httpx.AsyncClient(
            verify=create_ssl_context(),
            follow_redirects=True,
            timeout=120.0
        ) as client:
            # 1. Get repomd.xml
            print("Fetching repomd.xml...")
            repomd_response = await client.get(repomd_url)
            repomd_response.raise_for_status()

            # 2. Find primary location
            print("Finding primary location...")
            primary_location = None
            try:
                root = ET.fromstring(repomd_response.content)
                ns = {'ns': 'http://linux.duke.edu/metadata/repo'}
                for data in root.findall('ns:data', ns):
                    if data.get('type') == 'primary':
                        location = data.find('ns:location', ns)
                        if location is not None:
                            primary_location = location.get('href')
                            break
                
                if not primary_location:
                    cleaned = re.sub(b'xmlns="[^"]+"', b'', repomd_response.content)
                    root = ET.fromstring(cleaned)
                    for data in root.findall('.//data'):
                        if data.get('type') == 'primary':
                            location = data.find('location')
                            if location is not None:
                                primary_location = location.get('href')
                                break
            except Exception as e:
                print(f"Error parsing repomd.xml: {str(e)}")
                return {}

            if not primary_location:
                print("Could not find primary location in repomd.xml")
                return {}

            # 3. Build correct primary URL - handle relative paths
            if primary_location.startswith('repodata/'):
                primary_url = f"{base_path}/{repo_name}/{primary_location}"
            else:
                # Absolute path - use as-is (shouldn't happen with our repos)
                primary_url = primary_location
            
            print(f"Primary metadata URL: {primary_url}")

            # 4. Stream and parse primary file
            packages = {}
            async with client.stream('GET', primary_url) as response:
                response.raise_for_status()
                
                # Initialize decompression
                decompressor = None
                is_gzip = False
                is_xz = False
                first_chunk = True
                parser = ET.XMLPullParser(['start', 'end'])
                package_count = 0
                
                async for chunk in response.aiter_bytes():
                    if first_chunk:
                        first_chunk = False
                        if chunk.startswith(b'\x1f\x8b'):
                            print("Detected GZIP format")
                            decompressor = zlib.decompressobj(zlib.MAX_WBITS | 16)
                            is_gzip = True
                        elif chunk.startswith(b'\xFD7zXZ\x00'):
                            print("Detected XZ format")
                            decompressor = lzma.LZMADecompressor()
                            is_xz = True
                        else:
                            print(f"Unknown compression format: {chunk[:6].hex()}")
                            return {}
                    
                    try:
                        if is_gzip:
                            data = decompressor.decompress(chunk)
                        elif is_xz:
                            data = decompressor.decompress(chunk)
                        else:
                            data = chunk
                        
                        if not data:
                            continue
                            
                        parser.feed(data)
                        for event, elem in parser.read_events():
                            if event == 'start' and elem.tag.endswith('package'):
                                current_pkg = {}
                            elif event == 'end':
                                if elem.tag.endswith('name'):
                                    current_pkg['name'] = elem.text
                                elif elem.tag.endswith('version'):
                                    current_pkg['version'] = elem.attrib
                                elif elem.tag.endswith('arch'):
                                    current_pkg['arch'] = elem.text
                                elif elem.tag.endswith('summary'):
                                    current_pkg['summary'] = elem.text
                                elif elem.tag.endswith('package') and 'name' in current_pkg:
                                    packages[current_pkg['name'].lower()] = {
                                        'name': current_pkg['name'],
                                        'version': current_pkg.get('version', {}),
                                        'arch': current_pkg.get('arch', ''),
                                        'summary': current_pkg.get('summary', '')
                                    }
                                    package_count += 1
                                    if package_count % 1000 == 0:
                                        print(f"Processed {package_count} packages...")
                                    elem.clear()
                    except Exception as e:
                        print(f"Error processing chunk: {str(e)}")
                        continue

            print(f"Found {len(packages)} packages total")
            
            # Cache results
            if packages:
                cache_file.parent.mkdir(exist_ok=True, parents=True)
                with open(cache_file, 'w') as f:
                    json.dump(packages, f)
                print(f"Cached results to {cache_file}")

            return packages

    except Exception as e:
        print(f"Error processing {repo_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}
