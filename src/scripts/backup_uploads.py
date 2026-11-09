#!/usr/bin/env python3
"""Download referenced live uploads through the admin API before a Render redeploy."""
import argparse
from datetime import datetime, timezone
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from zipfile import ZipFile, ZIP_STORED
import httpx

MAX_FILE_BYTES = 50 * 1024 * 1024
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / 'backups'
UUID_PATTERN = r'[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}'


def referenced_files(snapshot, api_path='/api/v1'):
    pattern = re.compile(re.escape(api_path.rstrip('/')+'/files/')+'('+UUID_PATTERN+r')(?![0-9a-fA-F-])')
    references = {}
    def walk(value, private=False):
        if isinstance(value, dict):
            for key,item in value.items():
                walk(item,private or key=='proofOfPayment')
        elif isinstance(value, list):
            for item in value: walk(item,private)
        elif isinstance(value, str):
            for match in pattern.finditer(value):
                identifier=match.group(1).lower()
                references[identifier] = references.get(identifier,False) or private
    walk(snapshot)
    return references


def write_json(path,value):
    with path.open('x',encoding='utf-8') as output:
        os.chmod(path,0o600)
        json.dump(value,output,indent=2,ensure_ascii=False)


def backup(api_url,site_url,email,password,output_root,transport=None):
    for value in (api_url,site_url):
        parsed=urlsplit(value)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Use HTTPS URLs without credentials, query strings or fragments.')
    folder=Path(output_root)/datetime.now(timezone.utc).strftime('best5-uploads-%Y%m%dT%H%M%S%fZ')
    folder.mkdir(mode=0o700,parents=True)
    manifest={'api':api_url,'files':[],'note':'Referenced uploads and an admin snapshot; not a complete PostgreSQL backup.'}
    with httpx.Client(base_url=api_url.rstrip('/')+'/',headers={'Origin':site_url.rstrip('/')},
                      timeout=90,follow_redirects=False,transport=transport) as client:
        signed_in=False
        try:
            response=client.post('auth/login',json={'email':email,'password':password,'remember':False})
            if response.status_code!=200:
                raise RuntimeError('Sign-in failed. Check the API address, login email and password.')
            signed_in=True
            user=response.json()
            if user.get('mustChangePassword'):
                raise RuntimeError('Complete your initial password change on the website first.')
            if not {'content:read','operations:read'}.issubset(set(user.get('permissions',[]))):
                raise RuntimeError('Use an account permitted to read both content and registrations.')
            response=client.get('admin/bootstrap')
            response.raise_for_status()
            snapshot=response.json()
            write_json(folder/'admin-snapshot.json',snapshot)
            files=referenced_files(snapshot,urlsplit(api_url).path)
            for identifier,private in sorted(files.items()):
                entry={'id':identifier,'private':private}
                destination=folder/('private' if private else 'public')/identifier
                destination.parent.mkdir(mode=0o700,exist_ok=True)
                try:
                    with client.stream('GET','files/'+identifier) as download:
                        if download.status_code!=200:
                            entry.update(status='missing' if download.status_code==404 else 'failed',httpStatus=download.status_code)
                            manifest['files'].append(entry)
                            continue
                        mime=download.headers.get('content-type','').split(';')[0]
                        if not (mime.startswith('image/') or mime=='application/pdf'):
                            raise ValueError('Unexpected download type')
                        digest=hashlib.sha256();size=0
                        with destination.open('xb') as target:
                            os.chmod(destination,0o600)
                            for chunk in download.iter_bytes():
                                size+=len(chunk)
                                if size>MAX_FILE_BYTES: raise ValueError('File exceeds backup limit')
                                digest.update(chunk);target.write(chunk)
                        if size==0: raise ValueError('Empty download')
                        entry.update(status='saved',path=str(destination.relative_to(folder)),type=mime,size=size,sha256=digest.hexdigest())
                except (httpx.HTTPError,ValueError,OSError) as error:
                    destination.unlink(missing_ok=True)
                    entry.update(status='failed',reason=type(error).__name__)
                manifest['files'].append(entry)
            write_json(folder/'uploads-manifest.json',manifest)
        finally:
            if signed_in:
                csrf=next((cookie.value for cookie in client.cookies.jar if cookie.name=='best5_csrf'),'')
                try:
                    client.post('auth/logout',json={},headers={'X-CSRF-Token':csrf})
                except httpx.HTTPError:
                    pass
    # Store UUID paths at the ZIP root so restoring into best5_uploads preserves URLs.
    archive=folder/'best5-uploads-backup.zip'
    with archive.open('xb') as target:
        os.chmod(archive,0o600)
        with ZipFile(target,'w',ZIP_STORED) as package:
            for item in folder.rglob('*'):
                if item.is_file() and item!=archive:
                    package.write(item,item.relative_to(folder))
    saved=sum(item['status']=='saved' for item in manifest['files'])
    failed=len(manifest['files'])-saved
    return folder,archive,saved,failed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url',default='https://api.best5football.co.za/api/v1')
    parser.add_argument('--site-url',default='https://best5football.co.za')
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args()
    email=input('Live admin email: ').strip()
    password=getpass('Live admin password (hidden): ')
    try:
        folder,archive,saved,failed=backup(args.api_url,args.site_url,email,password,args.output)
    except (httpx.HTTPError,RuntimeError,ValueError,OSError) as error:
        print('Backup could not complete: '+(str(error) if isinstance(error,(RuntimeError,ValueError)) else type(error).__name__))
        raise SystemExit(1)
    print(f'Backup folder: {folder}\nBackup ZIP: {archive}\nSaved: {saved}; missing or failed: {failed}')
    print('This backup contains private application data. Never put it in public_html or Git.')
    print('Review uploads-manifest.json. This is not a complete database backup.')
    if failed:
        print('Some uploads could not be recovered. Keep the running service unchanged while checking the manifest.')
        raise SystemExit(2)

if __name__=='__main__':
    main()
