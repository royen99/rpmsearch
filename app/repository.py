import gzip
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta
import httpx
from typing import Dict, List, Optional

class RepositoryClient:
    def __init__(self, base_url: str, release_api_url: str):
        self.base_url = base_url.rstrip('/')
        self.release_api_url = release_api_url
        self.cache_dir = Path("/tmp/query_cache")
        self.cache_dir.mkdir(exist_ok=True)
        self.session = httpx.AsyncClient(timeout=30.0)
        self.versions_cache = None
        self.versions_cache_time = None

    async def get_available_versions(self) -> Dict[str, str]:
        """Fetch available versions from release API with caching"""
        if self.versions_cache and datetime.now() - self.versions_cache_time < timedelta(hours=1):
            return self.versions_cache

        try:
            response = await self.session.get(self.release_api_url)
            response.raise_for_status()
            data = response.json()
            self.versions_cache = data.get("repodata-tags", {})
            self.versions_cache_time = datetime.now()
            return self.versions_cache
        except Exception as e:
            raise RuntimeError(f"Failed to fetch versions: {str(e)}")

    async def get_repo_metadata(self, repo_name: str, version: Optional[str] = None) -> Dict:
        """Get metadata for a repository at specific version"""
        versions = await self.get_available_versions()
        version_path = versions.get(version, version if version else "current")
        repo_url = f"{self.base_url}/{version_path}/{repo_name}"
        repomd_url = f"{repo_url}/repodata/repomd.xml"
        
        try:
            # Fetch repomd.xml
            response = await self.session.get(repomd_url)
            response.raise_for_status()
            
            # Completely namespace-agnostic parsing
            xml_clean = self._clean_xml_namespaces(response.text)
            root = ET.fromstring(xml_clean)
            
            # Find primary metadata location
            primary_data = None
            for data in root.findall('data'):
                if data.get('type') == 'primary':
                    location = data.find('location')
                    if location is not None:
                        href = location.get('href')
                        primary_data = {
                            'href': href,
                            'format': 'xml.gz' if href.endswith('.xml.gz') else 'sqlite'
                        }
                    break

            if not primary_data:
                raise ValueError("Primary metadata not found in repomd.xml")

            # Fetch and parse primary metadata
            primary_url = f"{repo_url}/{primary_data['href']}"
            response = await self.session.get(primary_url)
            response.raise_for_status()

            if primary_data['format'] == 'xml.gz':
                return await self._parse_primary_xml(io.BytesIO(response.content))
            raise ValueError("Only XML.gz metadata format is currently supported")

        except Exception as e:
            raise RuntimeError(f"Failed to fetch repository metadata: {str(e)}")

    def _clean_xml_namespaces(self, xml_content: str) -> str:
        """Remove all namespace declarations from XML"""
        return re.sub(r'\sxmlns(:[a-z0-9]+)?="[^"]+"', '', xml_content)

    async def _parse_primary_xml(self, file_obj) -> Dict:
        """Parse primary.xml.gz with no namespace dependencies"""
        packages = {}
        with gzip.open(file_obj) as f:
            xml_clean = self._clean_xml_namespaces(f.read().decode('utf-8'))
            root = ET.fromstring(xml_clean)
            
            for pkg in root.findall('package'):
                name_elem = pkg.find('name')
                if name_elem is None or not name_elem.text:
                    continue
                    
                packages[name_elem.text.lower()] = {
                    'name': name_elem.text,
                    'version': pkg.find('version').attrib if pkg.find('version') is not None else {},
                    'arch': pkg.find('arch').text if pkg.find('arch') is not None else None,
                    'summary': pkg.find('summary').text if pkg.find('summary') is not None else "",
                    'description': (pkg.find('description').text 
                                  if pkg.find('description') is not None 
                                  else None),
                    'size': pkg.find('size').attrib if pkg.find('size') is not None else {}
                }
        return packages
