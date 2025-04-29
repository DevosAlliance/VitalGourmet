from pydal import DAL
from gluon.tools import Auth

# Função de conexão dinâmica com o banco de suporte
def conectar_banco_suporte():
    db_suporte = DAL(
        'mysql+mysqlconnector://lucas:!zJbfC!yamNVbJSnfPNJqN$1@srv647131.hstgr.cloud/suportemsg',
        migrate_enabled=False
    )

    db_suporte.define_table('clientes',
        Field('nome', 'string', required=True),
        Field('cpf_cnpj', 'string', required=True, label='CPF/CNPJ'),
        Field('email', 'string', requires=IS_EMAIL(), label='E-mail'),
        Field('telefone', 'string', label='Telefone'),
        Field('site', 'string', requires=IS_URL(), label='URL do Site'),
        Field('password', 'password', requires=CRYPT(), label='Senha'),
        Field('criado_em', 'datetime', default=request.now, writable=False, readable=False)
    )

    db_suporte.define_table('servicos',
        Field('cliente_id', 'reference clientes', label="Cliente", required=True),
        Field('nome', 'string', required=True),
        Field('descricao', 'text'),
        Field('valor', 'decimal(10, 2)', required=True, label="Valor (R$)"),
        Field('periodicidade', 'integer', required=True, label="Periodicidade (meses)"),
        Field('dia_vencimento', 'integer', requires=IS_INT_IN_RANGE(1, 32), label="Dia de vencimento"),
        Field('inicio', 'date', required=True, label="Início"),
        Field('fim', 'date', label="Fim"),
        Field('criado_em', 'datetime', default=request.now, writable=False, readable=False)
    )

    db_suporte.define_table('contas_receber',
        Field('servico_id', 'reference servicos', ondelete='CASCADE', label="Serviço"),
        Field('valor', 'decimal(10, 2)', required=True, label="Valor (R$)"),
        Field('data_prevista', 'date', required=True, label="Data Prevista"),
        Field('foi_pago', 'boolean', default=False, label="Foi Pago"),
        Field('criado_em', 'datetime', default=request.now, writable=False, readable=False)
    )


    # Tabela para tickets
    db_suporte.define_table('tickets',
        Field('cliente_id', 'reference clientes', label="Cliente"),
        Field('protocolo', 'string', default=lambda: str(uuid.uuid4())[:8].upper(), writable=False, readable=True, unique=True),
        Field('categoria', 'string', requires=IS_IN_SET(['Sugestão', 'Reclamação', 'Suporte']), label="Categoria"),
        Field('titulo', 'string', requires=IS_NOT_EMPTY(), label="Título"),
        Field('descricao', 'text', label="Descrição"),
        Field('evidencia', 'upload', label="Print de Evidência"),
        Field('status', 'string', default='Aberto', requires=IS_IN_SET(['Aberto', 'Em Progresso', 'Fechado']), label="Status"),
        Field('criado_em', 'datetime', default=request.now, writable=False),
    )

    # Tabela para mensagens do chat
    db_suporte.define_table('mensagens',
        Field('ticket_id', 'reference tickets', label="Ticket"),
        Field('remetente', 'string', label="Remetente"),
        Field('mensagem', 'text', requires=IS_NOT_EMPTY(), label="Mensagem"),
        Field('criado_em', 'datetime', default=request.now, writable=False),
    )
    return db_suporte

# Decorador para verificar login do cliente
def requires_client_login(f):
    """Decorator para verificar se o cliente está autenticado."""
    def wrapper(*args, **kwargs):
        if not session.cliente_id:  # Verifica se o cliente está logado
            session.flash = 'Faça login para continuar.'
            redirect(URL('clientesup', 'login'))
        return f(*args, **kwargs)
    return wrapper







@auth.requires_login()
def login():
    db_suporte = conectar_banco_suporte()  # Conexão dinâmica com o banco de suporte

    # Obtém o host atual (domínio principal)
    site_atual = f"https://{request.env.http_host}"

    # Tentativa de login automático com base na URL
    cliente = db_suporte(db_suporte.clientes.site.contains(site_atual)).select().first()

    if cliente:
        # Configura os dados do cliente para envio ao frontend
        response.headers['X-Automatic-Login'] = 'true'  # Sinaliza login automático no frontend
        response.headers['X-Cliente-ID'] = str(cliente.id)
        response.headers['X-Cliente-Nome'] = cliente.nome
        response.headers['X-Cliente-Email'] = cliente.email

        session.cliente_id = cliente.id
        session.flash = f"Bem-vindo, {cliente.nome}!"
        db_suporte.close()
        redirect(URL('clientesup', 'dashboard'))

    # Login manual
    if request.post_vars:
        email = request.post_vars.get('email')
        password = request.post_vars.get('password')

        cliente = db_suporte(db_suporte.clientes.email == email).select().first()
        if cliente and CRYPT()(password)[0] == cliente.password:
            session.cliente_id = cliente.id
            session.flash = f"Bem-vindo, {cliente.nome}!"
            db_suporte.close()
            redirect(URL('clientesup', 'dashboard'))
        else:
            response.flash = "E-mail ou senha inválidos."

    db_suporte.close()
    return dict(site_atual=site_atual)












# Logout do cliente
def logout():
    session.cliente_id = None
    session.flash = 'Você saiu do sistema.'
    redirect(URL('clientesup', 'login'))

# Dashboard
@requires_client_login
def dashboard():
    db_suporte = conectar_banco_suporte()
    cliente_id = session.cliente_id
    cliente = db_suporte.clientes(cliente_id) or redirect(URL('clientesup', 'login'))
    db_suporte.close()
    return dict(cliente=cliente)

# Listagem de serviços vigentes
@requires_client_login
def servicos_vigentes():
    db_suporte = conectar_banco_suporte()
    cliente_id = session.cliente_id
    servicos = db_suporte(db_suporte.servicos.cliente_id == cliente_id).select()
    db_suporte.close()
    return dict(servicos=servicos)

# Listagem de contas a pagar
@requires_client_login
def contas_pagar():
    db_suporte = conectar_banco_suporte()
    cliente_id = session.cliente_id

    contas = db_suporte(
        (db_suporte.contas_receber.servico_id == db_suporte.servicos.id) &
        (db_suporte.servicos.cliente_id == cliente_id) &
        (db_suporte.contas_receber.foi_pago == False)
    ).select(db_suporte.contas_receber.ALL, db_suporte.servicos.nome)

    dados_bancarios = {
        "cnpj": "48.909.124/0001-10",
        "banco": "Banco Inter",
        "agencia": "0001",
        "conta": "28563381-3",
        "pix": "48.909.124/0001-10",
        "qrcode_url": URL('static', 'images/qrcode_pix.png')
    }

    db_suporte.close()  # Fecha a conexão
    return dict(contas=contas, dados_bancarios=dados_bancarios)

# Abertura de tickets
@requires_client_login
def abrir_ticket():
    db_suporte = conectar_banco_suporte()
    cliente_id = session.cliente_id

    if request.post_vars:
        try:
            ticket_id = db_suporte.tickets.insert(
                cliente_id=cliente_id,
                categoria=request.post_vars.categoria,
                titulo=request.post_vars.titulo,
                descricao=request.post_vars.descricao,
            )
            db_suporte.close()
            session.flash = "Ticket criado com sucesso!"
            redirect(URL('clientesup', 'listar_tickets', args=[ticket_id]))
        except HTTP as e:
            if e.status == 303:
                raise e
            else:
                db.rollback()
                session.flash = f'Erro ao criar Ticket: {str(e)}'
                redirect(URL('clientesup', 'dashboard'))

        except Exception as e:
            db.rollback()
            session.flash = f'Erro ao criar Ticket: {str(e)}'
            redirect(URL('financeiro', 'create_lancamento_cliente'))

    db_suporte.close()
    return dict()

    

# Listagem de tickets
@requires_client_login
def listar_tickets():
    db_suporte = conectar_banco_suporte()
    cliente_id = session.cliente_id

    protocolo = request.vars.protocolo or None
    categoria = request.vars.categoria or None

    query = (db_suporte.tickets.cliente_id == cliente_id)
    if protocolo:
        query &= (db_suporte.tickets.protocolo.contains(protocolo))
    if categoria:
        query &= (db_suporte.tickets.categoria == categoria)

    tickets = db_suporte(query).select(orderby=~db_suporte.tickets.criado_em)
    db_suporte.close()
    return dict(tickets=tickets, protocolo=protocolo, categoria=categoria)

# Visualização de tickets
@requires_client_login
def ver_ticket():
    db_suporte = conectar_banco_suporte()
    ticket_id = request.args(0) or redirect(URL('clientesup', 'listar_tickets'))
    ticket = db_suporte.tickets(ticket_id) or redirect(URL('clientesup', 'listar_tickets'))

    if ticket.cliente_id != session.cliente_id:
        db_suporte.close()
        session.flash = "Acesso não permitido."
        redirect(URL('clientesup', 'listar_tickets'))

    mensagens = db_suporte(db_suporte.mensagens.ticket_id == ticket.id).select(orderby=db_suporte.mensagens.criado_em)

    if request.post_vars:
        db_suporte.mensagens.insert(
            ticket_id=ticket.id,
            remetente='Cliente',
            mensagem=request.post_vars.mensagem,
        )
        db_suporte.close()
        redirect(URL('clientesup', 'ver_ticket', args=[ticket.id]))

    db_suporte.close()
    return dict(ticket=ticket, mensagens=mensagens)

# API para obter mensagens associadas a tickets
@requires_client_login
def api_get_mensagens():
    db_suporte = conectar_banco_suporte()
    ticket_id = request.args(0) or redirect(URL('clientesup', 'listar_tickets'))

    mensagens = db_suporte(db_suporte.mensagens.ticket_id == ticket_id).select(
        orderby=db_suporte.mensagens.criado_em
    ).as_list()

    db_suporte.close()
    return response.json(mensagens)
