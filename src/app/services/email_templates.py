"""BEST5 HTML email layouts: inline styles, table layout and plain-text fallbacks."""
from html import escape
from urllib.parse import urljoin, urlsplit
from app.core.config import settings
from app.db.models import Document


def logo_url(db=None):
    configured=settings.email_logo_url
    if not configured and db is not None:
        document=db.get(Document,'settings')
        configured=((document.value.get('branding') or {}).get('mainLogo') if document else None)
    configured=configured or '/assets/images/logo/smt_logo.png'
    value=urljoin(settings.frontend_url.rstrip('/')+'/',configured)
    parsed=urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname:
        return urljoin(settings.frontend_url.rstrip('/')+'/','assets/images/logo/smt_logo.png')
    return value


def frame(*,title,eyebrow,content,button_label,button_url,preheader,logo=None,notice=''):
    parsed=urlsplit(button_url)
    if parsed.scheme not in ('http','https') or not parsed.hostname:
        raise ValueError('Email buttons require an absolute HTTP(S) URL')
    title,eyebrow,button_label,button_url,preheader=map(escape,(title,eyebrow,button_label,button_url,preheader))
    logo=escape(logo or logo_url())
    site=escape(settings.frontend_url.rstrip('/'))
    notice_html=f'<tr><td style="padding:0 32px 28px;color:#aabbaf;font-size:13px;line-height:21px;">{escape(notice)}</td></tr>' if notice else ''
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="dark"><title>{title}</title>
<style>@media only screen and (max-width:620px){{.email-shell{{width:100%!important}}.outer{{padding:20px 12px!important}}.email-title{{font-size:32px!important;line-height:37px!important}}}}</style></head>
<body bgcolor="#07100c" style="margin:0;padding:0;background-color:#07100c;font-family:Arial,Helvetica,sans-serif;color:#f5f7f4;-webkit-text-size-adjust:100%;">
<div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#07100c"><tr><td class="outer" align="center" style="padding:40px 16px;">
<table role="presentation" class="email-shell" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;">
<tr><td style="padding:0 0 24px;"><table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr><td width="74" style="vertical-align:middle;"><a href="{site}" style="text-decoration:none;"><img src="{logo}" width="60" height="62" alt="BEST5" style="display:block;border:0;width:60px;height:62px;object-fit:contain;"></a></td><td style="vertical-align:middle;"><a href="{site}" style="color:#f5f7f4;text-decoration:none;font-size:24px;font-weight:900;letter-spacing:1px;">BEST<span style="color:#c8ff4b;">5</span></a><div style="padding-top:5px;font-size:10px;letter-spacing:3px;line-height:15px;color:#aabbaf;">FOOTBALL EXHIBITION</div></td></tr></table></td></tr>
<tr><td bgcolor="#0d1d14" style="background-color:#0d1d14;border:1px solid #293d30;border-radius:22px;overflow:hidden;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td height="5" bgcolor="#c8ff4b" style="height:5px;background-color:#c8ff4b;font-size:0;line-height:0;border-radius:22px 22px 0 0;">&nbsp;</td></tr>
<tr><td style="padding:34px 32px 14px;color:#c8ff4b;font-size:11px;font-weight:700;letter-spacing:3px;line-height:18px;text-transform:uppercase;">{eyebrow}</td></tr>
<tr><td class="email-title" style="padding:0 32px 24px;color:#f5f7f4;font-size:40px;font-weight:800;line-height:45px;letter-spacing:-1px;">{title}</td></tr>
<tr><td style="padding:0 32px;color:#c0cec5;font-size:16px;line-height:27px;">{content}</td></tr>
<tr><td style="padding:28px 32px 16px;"><table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr><td align="center" bgcolor="#c8ff4b" style="background-color:#c8ff4b;border:1px solid #c8ff4b;border-radius:28px;mso-padding-alt:17px 28px;"><a href="{button_url}" target="_blank" style="display:inline-block;padding:17px 28px;color:#07100c;font-size:14px;font-weight:800;line-height:20px;text-align:center;text-decoration:none;border-radius:28px;">{button_label} &rarr;</a></td></tr></table></td></tr>
<tr><td style="padding:0 32px 28px;color:#8fa497;font-size:12px;line-height:20px;">Button not working? <a href="{button_url}" style="color:#c8ff4b;text-decoration:underline;">Open this link instead</a>.</td></tr>
{notice_html}
</table></td></tr>
<tr><td style="padding:24px 8px 0;color:#8fa497;font-size:12px;line-height:20px;text-align:center;"><strong style="color:#bdccc2;">BEST5 Football Exhibition</strong><br>Football. Community. One unforgettable experience.<br><a href="{site}" style="display:inline-block;margin-top:10px;color:#c8ff4b;text-decoration:none;">Visit the website &rarr;</a></td></tr>
</table></td></tr></table></body></html>'''


def invitation_email(name,role,link,db=None):
    name,role=escape(name),escape(role.replace('_',' ').title())
    content=f'''<p style="margin:0 0 18px;">Hello <strong style="color:#f5f7f4;">{name}</strong>,</p>
<p style="margin:0 0 22px;">You’re invited to join the BEST5 team. Your account is ready &mdash; choose your password to get started.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#152b1d" style="background-color:#152b1d;border:1px solid #304b37;border-radius:12px;"><tr><td style="padding:16px 18px;font-size:11px;letter-spacing:2px;font-weight:bold;color:#92ab9b;">YOUR ROLE</td><td align="right" style="padding:16px 18px;color:#c8ff4b;font-size:14px;font-weight:bold;">{role}</td></tr></table>
<p style="margin:20px 0 0;color:#c0cec5;">This private link is valid for <strong style="color:#f5f7f4;">48 hours</strong> and can be used once. No temporary password is needed.</p>'''
    return frame(title='You’re on the team.',eyebrow='Your BEST5 invitation',content=content,button_label='Create your password',button_url=link,preheader='Welcome to BEST5. Set your password and join the team.',logo=logo_url(db),notice='Once your password is set, sign in with your invited email address. If you weren’t expecting this invitation, contact the organiser.')


def password_reset_email(link,db=None):
    content='<p style="margin:0 0 16px;">We received a request to reset your BEST5 account password.</p><p style="margin:0;">Choose a new password using the button below. This link expires in <strong style="color:#f5f7f4;">30 minutes</strong> and can be used only once.</p>'
    return frame(title='Back in the game.',eyebrow='Password recovery',content=content,button_label='Reset your password',button_url=link,preheader='Reset your BEST5 password securely.',logo=logo_url(db),notice='Didn’t request this? You can ignore this email. Your password will stay the same.')


def notification_email(subject,body,db=None):
    content=''.join(f'<p style="margin:0 0 16px;">{escape(paragraph).replace(chr(10),"<br>")}</p>' for paragraph in body.split('\n\n'))
    return frame(title=subject,eyebrow='An update from BEST5',content=content,button_label='Visit BEST5',button_url=settings.frontend_url,preheader=subject,logo=logo_url(db))


def application_email(kind,name,reference,db=None,stall_fee=None):
    from urllib.parse import urlencode
    link=settings.frontend_url.rstrip('/')+'/application-status#'+urlencode({'reference':reference})
    label='team' if kind=='team' else 'vendor'
    details=('Your application and proof of payment are pending review.' if kind=='team' else 'Your vendor application is pending review. Contact the organiser for payment instructions.')
    if kind=='vendor' and stall_fee is not None:
        details += f' Your stall fee is R{stall_fee:,.0f}.'
    content=f'''<p style="margin:0 0 18px;">Thank you for registering <strong style="color:#f5f7f4;">{escape(name)}</strong> with BEST5.</p>
<p style="margin:0 0 20px;">{details}</p><div style="padding:20px;background:#152b1d;border:1px solid #304b37;border-radius:12px;"><p style="margin:0 0 8px;font-size:11px;letter-spacing:2px;">YOUR APPLICATION REFERENCE</p><strong style="color:#c8ff4b;font-size:23px;">{escape(reference)}</strong></div><p style="margin:20px 0 0;">Keep this reference. Use it with the email address you registered with to check your status.</p>'''
    html=frame(title='Application received.',eyebrow=f'Your BEST5 {label} registration',content=content,button_label='Check application status',button_url=link,preheader=f'Your reference: {reference}. Check your application status.',logo=logo_url(db),notice='Submission does not confirm your place. The registration team will review your application.')
    text=f'Thank you for registering {name}.\nYour reference is {reference}.\n{details}\nCheck application status: {link}\nEnter your reference and registered email address. Submission does not confirm your place.'
    return text,html


def submission_email(kind, value, db=None):
    label = 'team' if kind == 'team' else 'vendor'
    name = value['teamName'] if kind == 'team' else value['business']
    link = settings.frontend_url.rstrip('/') + f'/admin/{label}-registrations'
    lines = [f'New {label} application: {name}', f"Reference: {value['id']}",
             f"Contact: {value.get('captain', value.get('contact', ''))}", f"Email: {value['email']}"]
    if kind == 'team':
        lines.append(f"Phone: {value['phone']}")
    text = '\n'.join(lines) + f'\nReview application: {link}'
    content = ''.join(f'<p style="margin:0 0 12px;">{escape(line)}</p>' for line in lines)
    html = frame(title='New application received.', eyebrow=f'BEST5 {label} submission',
                 content=content, button_label='Review applications', button_url=link,
                 preheader=f'New {label} application: {name}', logo=logo_url(db),
                 notice='Sign in to review this application. Payment proofs are available only in the admin area.')
    return text, html
