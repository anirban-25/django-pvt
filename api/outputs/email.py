import os
from os.path import basename
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import COMMASPACE, formatdate

from django.conf import settings


def send_email(
    send_to,
    send_cc,
    send_bcc,
    subject,
    text,
    files=None,
    mime_type="plain",
    server="localhost",
    use_tls=True,
):
    assert isinstance(send_to, list)

    if settings.ENV != "prod":
        subject = f"[TEST] {subject}"

    msg = MIMEMultipart()
    msg["From"] = settings.EMAIL_HOST_USER
    msg["To"] = COMMASPACE.join(send_to)
    msg["Cc"] = COMMASPACE.join(send_cc)
    msg["Bcc"] = COMMASPACE.join(send_bcc)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject

    msg.attach(MIMEText(text, mime_type))

    for f in files or []:
        file_content = open(f, "rb").read()

        if f.lower().endswith((".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif")):
            image = MIMEImage(file_content, name=basename(f))
            msg.attach(image)
        else:
            pdf = MIMEApplication(file_content, Name=basename(f))
            pdf["Content-Disposition"] = 'attachment; filename="%s"' % basename(f)
            msg.attach(pdf)

    smtp = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)

    if use_tls:
        smtp.starttls()

    smtp.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
    smtp.sendmail(
        settings.EMAIL_HOST_USER, send_to + send_cc + send_bcc, msg.as_string()
    )
    smtp.close()
