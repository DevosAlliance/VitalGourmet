import hmac
import hashlib
import subprocess
import json
import logging
import os
from gluon import current

# Configurar logging de forma dinâmica usando o nome da aplicação
app_name = current.request.application
log_file_path = os.path.join(current.request.folder, 'private', 'webhook.log')

logging.basicConfig(filename=log_file_path, level=logging.DEBUG)

def webhook():
    GITHUB_SECRET = '123456'
    try:
        logging.debug("Received webhook request")

        # Read the raw request body
        raw_body = current.request.body.read()
        if not raw_body:
            logging.error("Request body is empty")
            raise HTTP(400, "Invalid request body")

        logging.debug("Request body read successfully")

        # Verify the signature
        received_signature = current.request.env.http_x_hub_signature
        if not received_signature:
            logging.error("Missing signature")
            raise HTTP(400, "Missing signature")

        logging.debug(f"Received signature: {received_signature}")

        signature = 'sha1=' + hmac.new(GITHUB_SECRET.encode(), raw_body, hashlib.sha1).hexdigest()
        if not hmac.compare_digest(signature, received_signature):
            logging.error("Invalid signature")
            raise HTTP(403, "Forbidden")

        logging.debug("Signature verified successfully")

        # Load the payload
        payload = json.loads(raw_body)
        logging.debug(f"Payload: {payload}")

        # Pull the latest code from GitHub
        repo_dir = current.request.folder  # Diretório dinâmico da aplicação
        result = subprocess.run(['git', 'pull'], cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode == 0:
            logging.debug("Git pull successful")
            return 'Updated successfully'
        else:
            logging.error(f"Git pull failed: {result.stderr.decode()}")
            return 'Update failed: ' + result.stderr.decode()
    except Exception as e:
        logging.error(f"Exception: {str(e)}")
        return str(e)
