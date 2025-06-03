# -*- coding: utf-8 -*-
"""MCP TP Correction Assistant

This script connects to Gmail, downloads the most recent email with a ZIP
attachment, extracts it, verifies required files, checks for expected
function definitions inside the TAD modules and replies with a summary
report. It follows the MCP (Modelo de Correcci\xc3\xb3n de Pr\xc3\xa1cticas) model
and can be integrated in n8n workflows.
"""

import base64
import email
import os
import re
import tempfile
from email.message import EmailMessage
from typing import Dict, List, Tuple

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these SCOPES, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

EXPECTED_FILES = {
    "tad_simple": re.compile(r"tad_simple", re.I),
    "tad_compuesto": re.compile(r"tad_compuesto", re.I),
    "tad_cola": re.compile(r"tad_cola", re.I),
    "app": re.compile(r"app|principal|farmacia", re.I),
}

def authenticate_gmail() -> "object":
    """Authenticate and return Gmail service object."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # The credentials.json file must be obtained from Google Cloud Console
    if not creds or not creds.valid:
        raise RuntimeError("Valid Gmail credentials not found. Run OAuth flow beforehand.")
    service = build("gmail", "v1", credentials=creds)
    return service

def get_latest_zip_message(service) -> Tuple[str, str]:
    """Return message id and subject of the latest email with a .zip attachment."""
    results = service.users().messages().list(userId="me", q="has:attachment filename:zip").execute()
    messages = results.get("messages", [])
    if not messages:
        return None, None
    message_id = messages[0]["id"]
    msg = service.users().messages().get(userId="me", id=message_id, format="metadata").execute()
    subject = next((h["value"] for h in msg.get("payload", {}).get("headers", []) if h["name"].lower() == "subject"), "")
    return message_id, subject

def download_zip_attachment(service, message_id: str) -> str:
    """Download the zip attachment from the specified message."""
    msg = service.users().messages().get(userId="me", id=message_id).execute()
    for part in msg["payload"].get("parts", []):
        if part.get("filename", "").lower().endswith(".zip"):
            att_id = part["body"]["attachmentId"]
            att = service.users().messages().attachments().get(userId="me", messageId=message_id, id=att_id).execute()
            data = base64.urlsafe_b64decode(att["data"])
            fd, path = tempfile.mkstemp(suffix=".zip")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            return path
    return None

def extract_zip(zip_path: str) -> str:
    import zipfile
    extract_dir = tempfile.mkdtemp(prefix="tp_zip_")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)
    return extract_dir

def locate_files(base_dir: str) -> Dict[str, str]:
    """Return a mapping from expected key to found filepath."""
    found = {}
    for root, _dirs, files in os.walk(base_dir):
        for f in files:
            for key, pattern in EXPECTED_FILES.items():
                if key not in found and pattern.search(f):
                    found[key] = os.path.join(root, f)
    return found

def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def check_tad_simple(content: str) -> Tuple[List[str], List[str]]:
    expected = [
        re.compile(r"crear\s*\(", re.I),
        re.compile(r"ver_", re.I),
        re.compile(r"modificar_", re.I),
        re.compile(r"copiar\s*\(", re.I),
        re.compile(r"asignar\s*\(", re.I),
    ]
    names = ["crear", "ver_", "modificar_", "copiar", "asignar"]
    found, missing = [], []
    for name, pattern in zip(names, expected):
        if pattern.search(content):
            found.append(name)
        else:
            missing.append(name)
    return found, missing

def check_tad_compuesto(content: str) -> Tuple[List[str], List[str]]:
    expected = [
        re.compile(r"crear\s*\(", re.I),
        re.compile(r"agregar\s*\(", re.I),
        re.compile(r"recuperar\s*\(", re.I),
        re.compile(r"tama\xC3\xb1o\s*\(|tamano\s*\(", re.I),
        re.compile(r"eliminar\s*\(", re.I),
        re.compile(r"es_vacio\s*\(|es_vac\xC3\xADo\s*\(", re.I),
    ]
    names = ["crear", "agregar", "recuperar", "tamano", "eliminar", "es_vacio"]
    found, missing = [], []
    for name, pattern in zip(names, expected):
        if pattern.search(content):
            found.append(name)
        else:
            missing.append(name)
    return found, missing

def generate_report(data: Dict[str, Tuple[List[str], List[str]]], found_files: Dict[str, str]) -> str:
    lines = []
    zip_found = "Sí" if found_files else "No"
    lines.append(f"ZIP encontrado: {zip_found}")
    missing = [key for key in EXPECTED_FILES if key not in found_files]
    if missing:
        lines.append(f"Archivos básicos presentes: No ({', '.join(missing)})")
    else:
        lines.append("Archivos básicos presentes: Sí")
    for key in ["tad_simple", "tad_compuesto"]:
        if key in found_files:
            found, miss = data.get(key, ([], []))
            lines.append(f"{key}: funciones encontradas {found}, faltantes {miss}")
        else:
            lines.append(f"{key}: archivo no hallado")
    if "tad_cola" in found_files:
        lines.append(f"TAD cola detectado: {os.path.basename(found_files['tad_cola'])}")
    if "app" in found_files:
        lines.append(f"App principal detectada: {os.path.basename(found_files['app'])}")
    overall_missing = any(data[key][1] for key in data)
    if overall_missing or missing:
        result = "Aprobado con observaciones" if not missing else "Rechazado"
    else:
        result = "Aprobado"
    lines.append(f"Resultado final: {result}")
    return "\n".join(lines)

def send_reply(service, message_id: str, subject: str, body: str) -> None:
    reply = EmailMessage()
    reply.set_content(body)
    reply["To"] = "me"
    reply["Subject"] = f"Revisi\xc3\xb3n TP: {subject}"
    reply["In-Reply-To"] = message_id
    encoded_message = base64.urlsafe_b64encode(reply.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": encoded_message, "threadId": message_id}).execute()

def main() -> None:
    try:
        service = authenticate_gmail()
        msg_id, subject = get_latest_zip_message(service)
        if not msg_id:
            print("No se encontró un correo con ZIP adjunto")
            return
        zip_path = download_zip_attachment(service, msg_id)
        if not zip_path:
            print("No se encontró adjunto ZIP en el mensaje")
            return
        extract_dir = extract_zip(zip_path)
        files = locate_files(extract_dir)
        results = {}
        if "tad_simple" in files:
            results["tad_simple"] = check_tad_simple(read_file(files["tad_simple"]))
        if "tad_compuesto" in files:
            results["tad_compuesto"] = check_tad_compuesto(read_file(files["tad_compuesto"]))
        report = generate_report(results, files)
        send_reply(service, msg_id, subject, report)
        print("Reporte enviado:")
        print(report)
    except HttpError as error:
        print(f"Ocurrió un error: {error}")

if __name__ == "__main__":
    main()
