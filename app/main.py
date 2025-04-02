from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import gzip
import xml.etree.ElementTree as ET
import httpx
from pathlib import Path
import os

app = FastAPI()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

REPO_BASE_URL = os.getenv("REPO_BASE_URL")
AVAILABLE_REPOS = ["rhel-8-for-x86_64-baseos-rpms", "rhel-8-for-x86_64-appstream-rpms", "rhel-9-for-x86_64-baseos-rpms", "rhel-9-for-x86_64-appstream-rpms","rhel-8-epel-rpms", "rhel-9-epel-rpms","codeready-builder-for-rhel-8-x86_64-rpms", "codeready-builder-for-rhel-9-x86_64-rpms"]

@app.get("/", response_class=HTMLResponse)
async def query_form(request: Request):
    return templates.TemplateResponse("query.html", {
        "request": request,
        "repos": AVAILABLE_REPOS
    })

@app.get("/api/search")
async def search_packages(
    package: str = Query(..., min_length=2),
    repo: str = Query(None)
):
    results = []
    repos_to_search = [repo] if repo else AVAILABLE_REPOS
    
    for repo_name in repos_to_search:
        try:
            packages = await get_repo_packages(repo_name)
            if package.lower() in packages:
                results.append({
                    "repo": repo_name,
                    "package": packages[package.lower()]
                })
        except Exception as e:
            continue
            
    return {"query": package, "results": results}

async def get_repo_packages(repo_name: str):
    """Cache and parse repository metadata"""
    cache_file = Path(f"/tmp/query_cache/{repo_name}.json")
    
    # Use cached data if fresh
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    
    # Fetch and parse primary.xml.gz
    url = f"{REPO_BASE_URL}/{repo_name}/repodata/primary.xml.gz"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        with gzip.open(io.BytesIO(response.content)) as f:
            tree = ET.parse(f)
    
    packages = {}
    for pkg in tree.findall('{*}package'):
        name = pkg.find('{*}name').text.lower()
        packages[name] = {
            "name": pkg.find('{*}name').text,
            "version": pkg.find('{*}version').attrib,
            "arch": pkg.find('{*}arch').text,
            "summary": pkg.find('{*}summary').text
        }
    
    # Cache results
    cache_file.parent.mkdir(exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(packages, f)
    
    return packages
