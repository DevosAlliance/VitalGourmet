# -*- coding: utf-8 -*-
from gluon.contrib.appconfig import AppConfig
from gluon.tools import Auth
from pydal import DAL, Field
from gluon.storage import Storage


TENANTS = {
    'hst.sistemasdevos.com.br': {
        'id': 'cliente1',
        'name': 'HST',
        'db_uri': 'mysql+mysqlconnector://lucas:!zJbfC!yamNVbJSnfPNJqN$1@srv647131.hstgr.cloud/hst',
        'theme': 'hst',
        'logo': 'logo_cliente1.png',
        'primary_color': '#4e73df',
        'secondary_color': '#f8f9fc'
    },
    'hst.sistemasdevos.com.br/dev': {
        'id': 'cliente2',
        'name': 'Cliente 2',
        'db_uri': 'mysql+mysqlconnector://lucas:!zJbfC!yamNVbJSnfPNJqN$1@srv647131.hstgr.cloud/hstdeveloper',
        'theme': 'theme_cliente2',
        'logo': 'logo_cliente2.png',
        'primary_color': '#1cc88a',
        'secondary_color': '#f0f0f0'
    },
    'demo.sistemasdevos.com.br': {
        'id': 'desenvolvimento',
        'name': 'Desenvolvimento',
        'db_uri': 'mysql+mysqlconnector://lucas:!zJbfC!yamNVbJSnfPNJqN$1@srv647131.hstgr.cloud/hstdeveloper',
        'theme': 'default',
        'logo': 'iconShrt.png',
        'primary_color': '#6f9b82',
        'secondary_color': '#f8f9fc'
    },
    'default': {
        'id': 'default',
        'name': 'VitalGourmet (Dev)',
        'db_uri': 'mysql+mysqlconnector://lucas:!zJbfC!yamNVbJSnfPNJqN$1@srv647131.hstgr.cloud/hstdeveloper',
        'theme': 'default',
        'logo': 'iconShrt.png',
        'primary_color': '#6f9b82',
        'secondary_color': '#f8f9fc'
    }
}

def get_current_tenant():
    host = request.env.http_host.split(':')[0] if request.env.http_host else 'localhost'
    path = request.env.path_info if request.env.path_info else ''
    
    if hasattr(session, '_tenant_override') and session._tenant_override and request.is_local:
        override = session._tenant_override
        if override in TENANTS:
            return Storage(TENANTS[override])
    
    matching_tenants = []
    
    for tenant_url, config in TENANTS.items():
        if tenant_url == 'default':
            continue
            
        tenant_host, *tenant_path_parts = tenant_url.split('/', 1)
        tenant_path = f"/{tenant_path_parts[0]}" if tenant_path_parts else ""
        
        if host == tenant_host and path.startswith(tenant_path):
            matching_tenants.append((config, len(tenant_path)))
    
    if matching_tenants:
        matching_tenants.sort(key=lambda x: x[1], reverse=True)
        return Storage(matching_tenants[0][0])
    
    if 'default' in TENANTS:
        return Storage(TENANTS['default'])
    
    return Storage(list(TENANTS.values())[0])

tenant = get_current_tenant()
session.tenant = tenant
response.title = tenant.name
response.files.append(URL('static', f'css/theme/{tenant.theme}.css'))

configuration = AppConfig(reload=True)

if not request.env.web2py_runtime_gae:
    db = DAL(
        tenant.db_uri,
        pool_size=configuration.get('db.pool_size'),
        migrate_enabled=configuration.get('db.migrate'),
        check_reserved=['all'],
        migrate=True,
        )
else:
    db = DAL('google:datastore+ndb')
    session.connect(request, response, db=db)

response.generic_patterns = [] 
if request.is_local and not configuration.get('app.production'):
    response.generic_patterns.append('*')

response.formstyle = 'bootstrap4_inline'
response.form_label_separator = ''

auth = Auth(db, host_names=configuration.get('host.names'))

# Define a tabela de tipos de usuário
db.define_table('user_type',
    Field('name', 'string', unique=True, required=True, label="Nome do Tipo"), 
    format='%(name)s'
)

# Define a tabela de setores
db.define_table('setor',
    Field('name', 'string', unique=True, required=True, label="Nome do Setor"),
    format='%(name)s'
)

# Função para obter todos os tipos de usuário ativos
def get_all_user_types():
    return db.select(db.user_type.name, orderby=db.user_type.name)

# Função para obter todos os setores ativos
def get_all_setores():
    return db.select(db.setor.name, orderby=db.setor.name)

# Função para obter lista de nomes de tipos de usuário
def get_user_type_names():
    return [row.name for row in get_all_user_types()]

# Função para obter lista de nomes de setores
def get_setor_names():
    return [row.name for row in get_all_setores()]

INITIAL_TIPOS_USUARIO = [
    'Administrador', 'Colaborador', 'Gestor', 'Paciente', 
    'Instrumentador', 'Paciente Convenio', 'Acompanhante', 
    'Hemodialise', 'Medico'
]

# Lista inicial de setores (para preservar os valores antigos)
INITIAL_SETORES = [
    'Administrador', 'Administrativo', 'Medico', 'Recepção', 
    'Enfermagem', 'Hemodialise', 'Nutrição', 'Cozinha', 
    'Faturamento', 'Radiologia', 'Serviços Gerais', 
    'Paciente', 'Paciente Convenio', 'Acompanhante'
]

# Popula os tipos de usuário iniciais se a tabela estiver vazia
if db(db.user_type.id > 0).count() == 0:
    for tipo in INITIAL_TIPOS_USUARIO:
        db.user_type.insert(name=tipo)

# Popula os setores iniciais se a tabela estiver vazia
if db(db.setor.id > 0).count() == 0:
    for setor in INITIAL_SETORES:
        db.setor.insert(name=setor)

# Commit das alterações iniciais
db.commit()

auth.settings.extra_fields['auth_user'] = [
    Field('cpf', 'string', unique=True, required=True, label="CPF"),
    Field('user_type', 'reference user_type', label="Tipo de usuário"),
    Field('setor_id', 'reference setor', label="Setor", default=None),
    Field('birth_date', 'date', label="Data de Nascimento", requires=IS_NOT_EMPTY()),
    Field('room', 'string', label="Quarto", default=None),
    Field('observations', 'text', label="Observações", default=None),
    Field('status', 'string', requires=IS_IN_SET(['Ativo', 'Inativo']), default='Ativo', label="Status"),
]

# Atualize a tabela auth_user para incluir os novos campos
auth.define_tables()


auth.settings.create_user_groups = False

auth.define_tables(username=False, signature=False)

def assign_user_to_group(row, ret):
    tipo_usuario = db.user_type(row.user_type).name
    grupo = db(db.auth_group.role == tipo_usuario).select().first()
    
    if grupo:
        auth.add_membership(group_id=grupo.id, user_id=ret)

db.auth_user._after_insert.append(assign_user_to_group)

user_types = db(db.user_type).select(orderby=db.user_type.name)
for ut in user_types:
    role = ut.name
    if not db(db.auth_group.role == role).count():
        auth.add_group(role, f'Usuários que são {role.lower()}s')

# Configurações de email e senha
mail = auth.settings.mailer
mail.settings.server = 'logging' if request.is_local else configuration.get('smtp.server')
mail.settings.sender = configuration.get('smtp.sender')
mail.settings.login = configuration.get('smtp.login')
mail.settings.tls = configuration.get('smtp.tls') or False
mail.settings.ssl = configuration.get('smtp.ssl') or False

auth.settings.registration_requires_verification = False
auth.settings.registration_requires_approval = False
auth.settings.reset_password_requires_verification = True

# Metadados da aplicação
response.meta.author = configuration.get('app.author')
response.meta.description = configuration.get('app.description')
response.meta.keywords = configuration.get('app.keywords')
response.meta.generator = configuration.get('app.generator')
response.show_toolbar = configuration.get('app.toolbar')

response.google_analytics_id = configuration.get('google.analytics_id')

# Scheduler, se necessário
if configuration.get('scheduler.enabled'):
    from gluon.scheduler import Scheduler
    scheduler = Scheduler(db, heartbeat=configuration.get('scheduler.heartbeat'))

# -------------------------------------------------------------------------

# Tabela intermediária de acompanhantes vinculados a pacientes
db.define_table('acompanhante_vinculo',
    Field('paciente_id', 'reference auth_user', required=True, label="Paciente"),
    Field('acompanhante_id', 'reference auth_user', required=True, label="Acompanhante"),
    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    auth.signature,
)

# Tabela de metas para valores esperados
db.define_table('meta',
    Field('categoria', 'string', unique=True, required=True, label="Categoria"),
    Field('valor_esperado', 'integer', required=True, default=0, label="Valor Esperado"),
)

# Tabela de estoque de ingredientes
db.define_table('estoque',
    Field('nome', 'string', required=True),
    Field('gramatura', 'string', required=True),
    auth.signature,
    format='%(nome)s',
)


# Tabela de horários de refeições com tipos dinâmicos
db.define_table('horario_refeicoes',
    Field('tipo_usuario', 'json', required=True, label="Tipos de Usuário"), 
    Field('refeicao', 'string', required=True), 
    Field('pedido_inicio', 'time', required=True),
    Field('pedido_fim', 'time', required=True),
    Field('servido_inicio', 'time', required=True),
    auth.signature,
    format='%(refeicao)s',
)



# Tabela de cardápio com tipos dinâmicos
db.define_table('cardapio',
    Field('nome', 'string', required=True, label="Nome do Prato"),
    Field('descricao', 'text', required=True, label="Descrição"),
    Field('tipo', 'string', requires=IS_IN_DB(db, 'horario_refeicoes.refeicao', '%(refeicao)s'), label="Tipo de Refeição"),
    Field('ingredientes', 'json', required=True, label="Ingredientes"), 
    Field('tipos_usuario', 'json', required=True, label="Tipos de Usuário"),
    Field('dias_semana', 'json', requires=IS_IN_SET(['Segunda-feira', 'Terca-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sabado', 'Domingo'], multiple=True), required=True, label="Dias da Semana"), 
    Field('foto_do_prato', 'text', label="Foto do Prato"),
    Field('preco', 'decimal(10, 2)', required=True, label="Preço"),
    format='%(nome)s',
)

# Tabela de solicitação de refeições
db.define_table('solicitacao_refeicao',
    Field('solicitante_id', 'reference auth_user', required=True),
    Field('is_acompanhante', 'boolean', label="É acompanhante?", default=False),
    Field('prato_id', 'reference cardapio', required=True),
    Field('quantidade_solicitada', 'integer', required=True),
    Field('preco', 'decimal(10, 2)', required=True, label="Preço"),
    Field('data_solicitacao', 'date', default=request.now, required=True, label="Data"),
    Field('descricao', 'text', label="Descrição", default=None),  # Novo campo para descrição opcional
    Field('status', 'string', requires=IS_IN_SET(['Pendente', 'Em Preparação', 'Finalizado']), default='Pendente', label="Status"),
    Field('forma_pagamento', 'string', requires=IS_IN_SET(['pix', 'credito', 'debito', 'transferencia', 'especie']), label="Forma de Pagamento"),
    Field('foi_pago', 'boolean', default=False, label="Foi pago?"),
    auth.signature,
)

# Tabela de pagamentos
db.define_table('pagamentos',
    Field('paciente_id', 'reference auth_user', required=True, label="Paciente"),
    Field('valor_pago', 'decimal(10, 2)', required=True, label="Valor Pago"),
    Field('data_pagamento', 'date', default=request.now, required=True, label="Data do Pagamento"),
    Field('descricao', 'string', label="Descrição"),
    auth.signature,
    format='%(valor_pago)s',
)



# Tabela de log geral para ações no sistema
db.define_table('log_sistema',
    Field('user_id', 'reference auth_user', required=True, label="Usuário"),
    Field('entidade', 'string', required=True, label="Entidade"),  # Ex: 'estoque', 'user', 'cardapio'
    Field('acao', 'string', requires=IS_IN_SET(['exclusao', 'edicao']), label="Ação"),
    Field('registro_id', 'integer', required=True, label="ID do Registro"),  # ID do registro na entidade
    Field('observacao', 'json', label="Observação"),  # Estado anterior em caso de alteração
    Field('dataH', 'datetime', default=request.now, writable=False, readable=True, label="Data e Hora"),
    auth.signature,
    format='%(acao)s - %(entidade)s - %(dataH)s'
)

db.define_table('user_balance',
    Field('user_id', 'reference auth_user', unique=True),
    Field('saldo_devedor', 'decimal(10,2)', default=0),
    Field('updated_at', 'datetime', default=request.now, update=request.now)
)

db.define_table('configuracoes',
    Field('nome', 'string', unique=True),
    Field('valor', 'text'),
    Field('descricao', 'text'),
    Field('tipo', 'string', default='string'),  # string, int, json, etc.
    format='%(nome)s',
    migrate=True
)

# Tabela de categorias de usuários
db.define_table('categoria_usuario',
    Field('nome', 'string', unique=True, required=True, label="Nome da Categoria"),
    Field('descricao', 'text', label="Descrição"),
    Field('cor', 'string', label="Cor de identificação", default="#6c757d"),
    Field('ativo', 'boolean', default=True, label="Ativo"),
    format='%(nome)s'
)

# Tabela de relacionamento entre categorias e tipos
db.define_table('categoria_tipo_usuario',
    Field('categoria_id', 'reference categoria_usuario', required=True),
    Field('tipo_id', 'reference user_type', required=True),
)

# Garantir que não haja duplicatas na tabela de relacionamento
db.categoria_tipo_usuario._before_insert.append(lambda f: 
    None if db((db.categoria_tipo_usuario.categoria_id == f.categoria_id) & 
              (db.categoria_tipo_usuario.tipo_id == f.tipo_id)).count() == 0 
    else False)


db.define_table('tipo_usuario_setor',
    Field('tipo_id', 'reference user_type', required=True, label="Tipo de Usuário"),
    Field('setor_id', 'reference setor', required=True, label="Setor Permitido"),
    format='%(tipo_id)s_%(setor_id)s'
)

# Adicionar validação de unicidade para par (tipo_id, setor_id)
db.tipo_usuario_setor._before_insert.append(lambda campos: 
    None if db((db.tipo_usuario_setor.tipo_id == campos.tipo_id) & 
              (db.tipo_usuario_setor.setor_id == campos.setor_id)).count() == 0 
    else False)

def get_tipos_por_categoria(nome_categoria):
    """
    Retorna os tipos de usuário pertencentes a uma determinada categoria.
    """
    # Busca o ID da categoria pelo nome
    categoria = db(db.categoria_usuario.nome == nome_categoria).select().first()
    if not categoria:
        return []
    
    # Busca os relacionamentos para esta categoria
    relacionamentos = db(db.categoria_tipo_usuario.categoria_id == categoria.id).select(
        db.categoria_tipo_usuario.tipo_id
    )
    
    if not relacionamentos:
        return []
    
    # Extrai os IDs dos tipos
    tipo_ids = [r.tipo_id for r in relacionamentos]
    
    # Busca os tipos de usuário
    tipos = db(db.user_type.id.belongs(tipo_ids)).select(
        orderby=db.user_type.name
    )
    
    return tipos

def get_setores_por_tipo(tipo_id):
    """Retorna lista de nomes de setores permitidos para um tipo de usuário"""
    setores = db(db.tipo_usuario_setor.tipo_id == tipo_id).select(
        db.setor.name,
        left=db.setor.on(db.tipo_usuario_setor.setor_id == db.setor.id)
    )
    return [s.name for s in setores]




def configurar_categorias_e_tipos():
    """
    Função para configurar as categorias e associar tipos de usuário existentes
    """
    # Verificar se a categoria "Colaboradores" existe
    categoria_colaboradores = db(db.categoria_usuario.nome == 'Colaboradores').select().first()
    
    # Se não existir, criar
    if not categoria_colaboradores:
        categoria_colaboradores_id = db.categoria_usuario.insert(
            nome='Colaboradores',
            descricao='Funcionários e colaboradores',
            cor='#28a745',
            ativo=True
        )
    else:
        categoria_colaboradores_id = categoria_colaboradores.id
        
    # Lista de tipos que devem pertencer à categoria Colaboradores
    tipos_colaboradores = ['Hemodiálise', 'Instrumentador', 'Gestor', 'Colaborador', 'Medico']
    
    # Buscar tipos de usuário existentes que devem ser associados
    tipos = db(db.user_type.name.belongs(tipos_colaboradores)).select()
    
    # Associar cada tipo à categoria, se ainda não estiver associado
    for tipo in tipos:
        # Verificar se já existe a associação
        associacao = db((db.categoria_tipo_usuario.categoria_id == categoria_colaboradores_id) & 
                       (db.categoria_tipo_usuario.tipo_id == tipo.id)).select().first()
        
        # Se não existir, criar
        if not associacao:
            db.categoria_tipo_usuario.insert(
                categoria_id=categoria_colaboradores_id,
                tipo_id=tipo.id
            )
    
    db.commit()
    return f"Configuração concluída. {len(tipos)} tipos de colaborador foram associados à categoria 'Colaboradores'."





class IS_VALID_USER_TYPES(object):
    def __init__(self, error_message="Tipo de usuário inválido"):
        self.error_message = error_message
        
    def __call__(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except:
                return (value, self.error_message)
        
        valid_types = get_user_type_names()
        for tipo in value:
            if tipo not in valid_types:
                return (value, self.error_message)
        return (value, None)
    
    # Garantir que as categorias básicas existam
    if db(db.categoria_usuario.id > 0).count() == 0:
        categorias_iniciais = [
            {'nome': 'Pacientes', 'descricao': 'Todos os tipos de pacientes', 'cor': '#007bff'},
            {'nome': 'Colaboradores', 'descricao': 'Funcionários e colaboradores', 'cor': '#28a745'},
            {'nome': 'Acompanhantes', 'descricao': 'Acompanhantes de pacientes', 'cor': '#17a2b8'}
        ]
        
        for cat in categorias_iniciais:
            db.categoria_usuario.insert(**cat)
        
        # Associar tipos iniciais às categorias
        pacientes_cat = db(db.categoria_usuario.nome == 'Pacientes').select().first()
        if pacientes_cat:
            tipos_paciente = db(db.user_type.name.belongs(['Paciente', 'Paciente Convenio'])).select()
            for tipo in tipos_paciente:
                db.categoria_tipo_usuario.insert(categoria_id=pacientes_cat.id, tipo_id=tipo.id)
        
        

# Aplica a validação à tabela de horários de refeições
db.horario_refeicoes.tipo_usuario.requires = IS_VALID_USER_TYPES()

# Aplica a validação à tabela de cardápio
db.cardapio.tipos_usuario.requires = IS_VALID_USER_TYPES()

# Configurar categorias e tipos de usuário
if db(db.categoria_usuario.id > 0).count() == 0:
    configurar_categorias_e_tipos()

db .commit ()

# Lógicas a serem implementadas: Solicitação de refeições junto à condição de baixa de estoque
