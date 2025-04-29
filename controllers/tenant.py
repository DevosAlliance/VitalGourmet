# controllers/tenant.py

def index():
    """
    Lista todos os tenants configurados
    """
    # TENANTS já está disponível como variável global do db.py
    # Não é necessário importar
    
    # Remove o tenant padrão da lista
    tenants = {k: v for k, v in TENANTS.items() if k != 'default'}
    
    return dict(tenants=tenants)

def switch():
    """
    Permite mudar de tenant para testes (somente em desenvolvimento)
    """
    if not request.is_local and not auth.has_membership('admin'):
        session.flash = 'Operação não permitida'
        redirect(URL('default', 'index'))
    
    tenant_host = request.args(0)
    if not tenant_host or tenant_host not in TENANTS:
        session.flash = 'Tenant não encontrado'
        redirect(URL('tenant', 'index'))
    
    # Guarda o host do tenant na sessão para simular acesso
    session._tenant_override = tenant_host
    session.flash = f'Alterado para o tenant: {TENANTS[tenant_host]["name"]}'
    redirect(URL('default', 'index'))

def reset():
    """
    Limpa a override do tenant na sessão
    """
    if '_tenant_override' in session:
        del session._tenant_override
    
    session.flash = 'Configuração de tenant restaurada para o padrão'
    redirect(URL('default', 'index'))