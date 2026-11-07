"""Render an invitation preview without creating tokens, queueing or sending email."""
import argparse
import base64
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from app.services.email_templates import invitation_email,logo_url
from app.core.config import settings

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='/tmp/best5-invitation-preview.html')
args=parser.parse_args()
html=invitation_email('Mohlatlego','admin',settings.frontend_url.rstrip('/')+'/admin/accept-invitation#token=preview-only')
# A self-contained preview can display the local asset without hosting it publicly.
logo=root.parent.parent/'football_exhibition_cms/src/public/assets/images/logo/smt_logo.png'
if logo.is_file(): html=html.replace(logo_url(),'data:image/png;base64,'+base64.b64encode(logo.read_bytes()).decode())
output=Path(args.output);output.write_text(html,encoding='utf-8')
print(f'Email preview saved: {output}')
