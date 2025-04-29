# models/tenant_config.py
import os
import json
from gluon.storage import Storage

# Configuração básica dos tenants
TENANTS = {
    'cliente1.exemplo.com': {
        'id': 'cliente1',
        'name': 'Cliente 1',
        'db_uri': 'mysql+mysqlconnector://usuario1:senha1@servidor1/db_cliente1',
        'theme': 'theme_cliente1',
        'logo': 'logo_cliente1.png',
        'primary_color': '#4e73df',
        'secondary_color': '#f8f9fc'
    },
    'cliente2.exemplo.com': {
        'id': 'cliente2',
        'name': 'Cliente 2',
        'db_uri': 'mysql+mysqlconnector://usuario2:senha2@servidor2/db_cliente2',
        'theme': 'theme_cliente2',
        'logo': 'logo_cliente2.png',
        'primary_color': '#1cc88a',
        'secondary_color': '#f0f0f0'
    },
    'default': {
        'id': 'default',
        'name': 'Sistema Padrão',
        'db_uri': 'mysql+mysqlconnector://lucas:!zJbfC!yamNVbJSnfPNJqN$1@srv647131.hstgr.cloud/hstdeveloper',
        'theme': 'default',
        'logo': 'iconShrt.png',
        'primary_color': '#4e73df',
        'secondary_color': '#f8f9fc'
    }
}

# Função simples para obter o tenant atual
def get_current_tenant():
    host = request.env.http_host.split(':')[0] if request.env.http_host else 'localhost'
    
    # Para desenvolvimento/admin: permite forçar um tenant específico
    if session.get('_tenant_override') and (request.is_local or auth.has_membership('admin')):
        override = session._tenant_override
        if override in TENANTS:
            return Storage(TENANTS[override])
    
    # Procura pelo tenant correspondente ao host
    if host in TENANTS:
        return Storage(TENANTS[host])
    
    # Se não encontrar, usa o tenant padrão
    return Storage(TENANTS['default'])