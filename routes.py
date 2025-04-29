# Configurar o manipulador de incorporação de usuários
def impersonation_before_request():
    if hasattr(current, 'response') and hasattr(current.response, 'impersonation_handler'):
        current.response.impersonation_handler()

# Define a função a ser executada antes de cada requisição
from gluon.globals import current
current.request.before_request.append(impersonation_before_request)