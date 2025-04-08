# Proposta de Implementação: Sistema de Agendamento Prévio de Refeições

## Visão Geral

O sistema atual de pedidos de refeições será expandido para permitir que usuários agendem seus pedidos antecipadamente, desde que os pratos não passem o `pedido_fim` (campo previsto na tabela `horario_refeicoes`) do horário atual. Esta implementação permitirá que os usuários planejem suas refeições para todo o dia logo pela manhã, enquanto a cozinha continuará visualizando apenas os pedidos relevantes para o período atual de preparo.

## Alterações Necessárias

### 1. MODELS

A estrutura atual dos `models` :

```python

TIPOS_USUARIO = ['Administrador', 'Colaborador', 'Gestor', 'Paciente', 'Instrumentador', 'Paciente Convenio', 'Acompanhante', 'Hemodialise', 'Medico']
SETORES = ['Administrador','Administrativo', 'Medico', 'Recepção', 'Enfermagem', 'Hemodialise', 'Nutrição', 'Cozinha', 'Faturamento', 'Radiologia', 'Serviços Gerais', 'Paciente', 'Paciente Convenio', 'Acompanhante']


# Definindo a tabela com migração habilitada
db.define_table('user_type',
    Field('name', 'string', unique=True, requires=IS_IN_SET(TIPOS_USUARIO), required=True), format='%(name)s'
)

db.define_table('setor',
    Field('name', 'string', unique=True, requires=IS_IN_SET(SETORES), required=True), format='%(name)s'
)

if db(db.user_type.id > 0).count() == 0:
    db.user_type.bulk_insert([{'name': tipo} for tipo in TIPOS_USUARIO])

if db(db.setor.id > 0).count() == 0:
    db.setor.bulk_insert([{'name': setor} for setor in SETORES])

auth.settings.extra_fields['auth_user'] = [
    Field('cpf', 'string', unique=True, required=True, label="CPF"),
    Field('user_type', 'reference user_type', label="Tipo de usuário"),
    Field('setor_id', 'reference setor', label="Setor", default=None),
    Field('birth_date', 'date', label="Data de Nascimento", requires=IS_NOT_EMPTY()),
    Field('room', 'string', label="Quarto", default=None),
    Field('observations', 'text', label="Observações", default=None),
    Field('status', 'string', requires=IS_IN_SET(['Ativo', 'Inativo']), default='Ativo', label="Status"),
]


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


# Tabela de horários de refeições
db.define_table('horario_refeicoes',
    Field('tipo_usuario', 'json', requires=IS_IN_SET(TIPOS_USUARIO, multiple=True), required=True, label="Tipos de Usuário"), 
    Field('refeicao', 'string', required=True), 
    Field('pedido_inicio', 'time', required=True),
    Field('pedido_fim', 'time', required=True),
    Field('servido_inicio', 'time', required=True),
    auth.signature,
    format='%(refeicao)s',
)


# Tabela de pratos
db.define_table('cardapio',
    Field('nome', 'string', required=True, label="Nome do Prato"),
    Field('descricao', 'text', required=True, label="Descrição"),
    Field('tipo', 'string', requires=IS_IN_DB(db, 'horario_refeicoes.refeicao', '%(refeicao)s'), label="Tipo de Refeição"), # A la carte, Livre, comum e etc
    Field('ingredientes', 'json', required=True, label="Ingredientes"), 
    Field('tipos_usuario', 'json', requires=IS_IN_SET(TIPOS_USUARIO, multiple=True), required=True, label="Tipos de Usuário"),
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
```

### 2. Adequação das APIs Existentes

#### Classes e regras

```python
class ConfiguracaoSistema:
    """Classe para gerenciar configurações do sistema que podem ser ajustadas via banco de dados"""
    
    @staticmethod
    def obter_configuracao(nome, padrao=None):
        """Obtém uma configuração do banco de dados ou retorna o valor padrão"""
        config = db(db.configuracoes.nome == nome).select().first()
        if not config:
            return padrao
            
        # Converte o valor de acordo com o tipo
        if config.tipo == 'int':
            return int(config.valor)
        elif config.tipo == 'float':
            return float(config.valor)
        elif config.tipo == 'boolean':
            return config.valor.lower() == 'true'
        elif config.tipo == 'json':
            try:
                return json.loads(config.valor)
            except:
                return padrao
        else:
            return config.valor
    
    @classmethod
    def obter_idade_minima_gratuidade(cls):
        return cls.obter_configuracao('idade_minima_gratuidade', 17)
    
    @classmethod
    def obter_idade_maxima_gratuidade(cls):
        return cls.obter_configuracao('idade_maxima_gratuidade', 60)
    
    @classmethod
    def obter_tipos_usuario_gratuidade_ilimitada(cls):
        tipos_padrao = ['Colaborador', 'Medico', 'Hemodialise', 'Instrumentador', 'Administrador', 'Gestor']
        return cls.obter_configuracao('tipos_usuario_gratuidade_ilimitada', tipos_padrao)
    
    @classmethod
    def obter_tipos_usuario_gratuidade_primeiro_prato(cls):
        tipos_padrao = ['Paciente Convenio', 'Paciente']
        return cls.obter_configuracao('tipos_usuario_gratuidade_primeiro_prato', tipos_padrao)
    
    @classmethod
    def obter_tipos_prato_sem_gratuidade(cls):
        tipos_padrao = ['A la carte', 'Livre', 'Bebidas']
        return cls.obter_configuracao('tipos_prato_sem_gratuidade', tipos_padrao)
        
    @classmethod
    def obter_tipos_paciente_acompanhante_herda_gratuidade(cls):
        tipos_padrao = ['Paciente Convenio']
        return cls.obter_configuracao('tipos_paciente_acompanhante_herda_gratuidade', tipos_padrao)
        
    @classmethod
    def acompanhante_herda_todos_pratos_gratuidade(cls):
        return cls.obter_configuracao('acompanhante_herda_todos_pratos_gratuidade', False)


class ValidadorUsuario:
    """Classe para validar as informações do usuário"""
    
    def __init__(self, usuario_id, db):
        self.db = db
        self.usuario = self.db.auth_user(usuario_id) if usuario_id else None
        self.hoje = request.now.date()
        self._inicializar()
    
    def _inicializar(self):
        """Inicializa as propriedades do validador"""
        if not self.usuario:
            raise ValueError("Usuário não encontrado.")
        
        self.user_type_id = self.usuario.user_type
        self.user_type_name = self.db.user_type[self.user_type_id].name if self.user_type_id else 'Visitante'
        
        # Verifica se é acompanhante
        acompanhante_vinculo = self.db(self.db.acompanhante_vinculo.acompanhante_id == self.usuario.id).select().first()
        
        self.is_acompanhante = False
        self.paciente_vinculado = None
        self.solicitante_real_id = self.usuario.id
        self.paciente_type_name = None
        
        if acompanhante_vinculo:
            self.is_acompanhante = True
            self.paciente_vinculado = self.db.auth_user(acompanhante_vinculo.paciente_id)
            if self.paciente_vinculado:
                self.solicitante_real_id = self.paciente_vinculado.id
                self.paciente_type_id = self.paciente_vinculado.user_type
                self.paciente_type_name = self.db.user_type[self.paciente_type_id].name if self.paciente_type_id else 'Visitante'
    
    def pode_solicitar_prato(self, prato):
        """Verifica se o usuário pode solicitar o prato especificado"""
        tipos_usuario_prato = (
            json.loads(prato.tipos_usuario) if isinstance(prato.tipos_usuario, str)
            else prato.tipos_usuario
        )
        
        return self.user_type_name in tipos_usuario_prato
    
    def obter_nome_observacao_pedido(self):
        """Obtém a observação padrão para o pedido baseado no tipo de usuário"""
        if self.is_acompanhante and self.paciente_vinculado:
            return f"Pedido de acompanhante: {self.usuario.first_name}"
        return ""
    
    def calcular_idade_paciente(self):
        """Calcula a idade do paciente vinculado se existir"""
        if not self.paciente_vinculado:
            return None
            
        return (self.hoje - self.paciente_vinculado.birth_date).days // 365
    
    def paciente_eh_convenio_idade_especial(self):
        """Verifica se o paciente vinculado é convênio e tem idade que qualifica para gratuidade"""
        if not self.is_acompanhante or not self.paciente_vinculado:
            return False
            
        idade = self.calcular_idade_paciente()
        if idade is None:
            return False
            
        # Verifica se o tipo do paciente está na lista de tipos que permitem herança de gratuidade
        tipos_permitidos = ConfiguracaoSistema.obter_tipos_paciente_acompanhante_herda_gratuidade()
        if self.paciente_type_name not in tipos_permitidos:
            return False
            
        idade_minima = ConfiguracaoSistema.obter_idade_minima_gratuidade()
        idade_maxima = ConfiguracaoSistema.obter_idade_maxima_gratuidade()
        
        return idade <= idade_minima or idade >= idade_maxima


class GerenciadorGratuidade:
    """Classe para gerenciar as regras de gratuidade para os pratos"""
    
    def __init__(self, validador_usuario, db):
        self.validador = validador_usuario
        self.db = db
        self.hoje = request.now.date()
    
    def verificar_pedidos_anteriores(self, prato_id=None, tipo_refeicao=None):
        """Verifica se existem pedidos anteriores gratuitos
        
        Args:
            prato_id: ID específico do prato a verificar
            tipo_refeicao: Tipo de refeição (Almoço, Jantar, Café, etc)
        """
        query = (
            (self.db.solicitacao_refeicao.solicitante_id == self.validador.solicitante_real_id) &
            (self.db.solicitacao_refeicao.data_solicitacao == self.hoje)
        )
        
        if prato_id:
            query &= (self.db.solicitacao_refeicao.prato_id == prato_id)
            
        pedidos = self.db(query).select(
            self.db.solicitacao_refeicao.ALL,
            self.db.cardapio.tipo,
            left=self.db.cardapio.on(self.db.solicitacao_refeicao.prato_id == self.db.cardapio.id)
        )
        
        # Filtra pedidos gratuitos por tipo de usuário
        pedido_paciente_gratis = pedidos.find(lambda p: not p.solicitacao_refeicao.is_acompanhante and p.solicitacao_refeicao.preco == 0)
        
        # Se tipo_refeicao for especificado, filtra pedidos gratuitos do acompanhante por tipo de refeição
        if tipo_refeicao:
            pedido_acompanhante_gratis = pedidos.find(
                lambda p: p.solicitacao_refeicao.is_acompanhante and 
                           p.solicitacao_refeicao.preco == 0 and 
                           p.cardapio.tipo == tipo_refeicao
            )
        else:
            pedido_acompanhante_gratis = pedidos.find(lambda p: p.solicitacao_refeicao.is_acompanhante and p.solicitacao_refeicao.preco == 0)
        
        return {
            'pedido_paciente_gratis': bool(pedido_paciente_gratis),
            'pedido_acompanhante_gratis': bool(pedido_acompanhante_gratis),
            'todos_pedidos': pedidos
        }
    
    def calcular_gratuidade(self, prato, quantidade=1):
        """Calcula a gratuidade e o preço final do prato"""
        tipos_sem_gratuidade = ConfiguracaoSistema.obter_tipos_prato_sem_gratuidade()
        
        # Se o tipo de prato não tem gratuidade, retorna o preço integral
        if prato.tipo in tipos_sem_gratuidade:
            return {
                'gratuidade': False,
                'motivo_gratuidade': None,
                'preco_total': prato.preco * quantidade
            }
        
        # Verifica gratuidade por tipo de usuário
        tipos_gratuidade_ilimitada = ConfiguracaoSistema.obter_tipos_usuario_gratuidade_ilimitada()
        if self.validador.user_type_name in tipos_gratuidade_ilimitada:
            return {
                'gratuidade': True,
                'motivo_gratuidade': 'Gratuidade ilimitada para médicos e colaboradores',
                'preco_total': 0
            }
        
        # Verifica gratuidade para primeiro prato
        tipos_gratuidade_primeiro = ConfiguracaoSistema.obter_tipos_usuario_gratuidade_primeiro_prato()
        pedidos = self.verificar_pedidos_anteriores(prato_id=prato.id)
        
        if self.validador.user_type_name in tipos_gratuidade_primeiro and not pedidos['pedido_paciente_gratis']:
            return {
                'gratuidade': True,
                'motivo_gratuidade': 'Primeiro prato do dia gratuito',
                'preco_total': 0
            }
        
        # Verifica gratuidade para acompanhante de paciente com idade especial
        if self.validador.is_acompanhante and self.validador.paciente_eh_convenio_idade_especial():
            # Verifica se já existe um pedido gratuito para este tipo de refeição
            pedidos_por_tipo = self.verificar_pedidos_anteriores(tipo_refeicao=prato.tipo)
            
            if not pedidos_por_tipo['pedido_acompanhante_gratis']:
                idade_minima = ConfiguracaoSistema.obter_idade_minima_gratuidade()
                idade_maxima = ConfiguracaoSistema.obter_idade_maxima_gratuidade()
                
                return {
                    'gratuidade': True,
                    'motivo_gratuidade': f'Primeiro {prato.tipo} gratuito para acompanhante de paciente (<{idade_minima+1} ou >{idade_maxima-1} anos)',
                    'preco_total': 0
                }
        
        # Sem gratuidade
        return {
            'gratuidade': False,
            'motivo_gratuidade': None,
            'preco_total': prato.preco * quantidade
        }


```
#### API de Listagem de Pratos

```python
def api_listar_pratos_para_usuario():
    try:
        solicitante_id = (
            request.vars.get('solicitante_id') or 
            (request.args(0) if len(request.args) > 0 else None) or 
            (auth.user.id if auth.user else None)
        )
        
        if not solicitante_id:
            raise ValueError("ID do solicitante não fornecido.")
        
        # classes de validação
        validador = ValidadorUsuario(solicitante_id, db)
        gerenciador = GerenciadorGratuidade(validador, db)
        
        dia_atual = _converter_dia_semana(datetime.datetime.now().strftime('%A'))
        
        # pratos permitidos para o usuário
        pratos_permitidos = db(
            (db.cardapio.tipos_usuario.contains(validador.user_type_name)) &
            (db.cardapio.dias_semana.contains(dia_atual))
        ).select()
        
        pratos_json = []
        
        for prato in pratos_permitidos:
            # horários de pedido para o prato
            horarios = _obter_horarios_prato(prato.tipo, validador.user_type_name)
            
            # Calcula a gratuidade e preço para o prato
            resultado_gratuidade = gerenciador.calcular_gratuidade(prato)
            
            pratos_json.append({
                'id': prato.id,
                'nome': prato.nome,
                'descricao': prato.descricao,
                'tipo': prato.tipo,
                'ingredientes': prato.ingredientes,
                'tipos_usuario': prato.tipos_usuario,
                'dias_semana': prato.dias_semana,
                'foto_do_prato': prato.foto_do_prato,
                'preco': float(resultado_gratuidade['preco_total']),
                'pedido_inicio': horarios['inicio'],
                'pedido_fim': horarios['fim'],
                'gratuidade': resultado_gratuidade['gratuidade'],
                'motivo_gratuidade': resultado_gratuidade['motivo_gratuidade']
            })
        
        # Ordenação
        pratos_json.sort(key=lambda prato: (prato['tipo'] == 'Bebidas', prato['nome']))
        
        return response.json({
            'status': 'success',
            'tipo_usuario': validador.user_type_name,
            'pratos': pratos_json
        })
        
    except Exception as e:
        print(f"Erro na API listar pratos: {str(e)}")
        return response.json({'status': 'error', 'message': str(e)})

```

#### API de Registro de Solicitação

```python
def api_registrar_solicitacao_refeicao():
    if request.env.request_method != 'POST':
        return response.json({'status': 'error', 'message': 'Método inválido. Use POST.'})
    
    try:
        solicitante_id = request.post_vars.get('solicitante_id') or (auth.user.id if auth.user else None)
        dados = request.post_vars
        
        # Validação básica dos dados
        prato_id = int(dados.get('pratoid'))
        quantidade_solicitada = int(dados.get('quantidade'))
        descricao = dados.get('descricao', None)
        status = dados.get('status', 'Pendente')
        
        # Verifica se o prato existe
        prato = db(db.cardapio.id == prato_id).select().first()
        if not prato:
            raise ValueError("O prato especificado não existe.")
        
        # Inicializa classes de validação e gratuidade
        validador = ValidadorUsuario(solicitante_id, db)
        gerenciador = GerenciadorGratuidade(validador, db)
        
        # Verifica se o usuário pode solicitar o prato
        if not validador.pode_solicitar_prato(prato):
            raise ValueError("Você não tem permissão para solicitar este prato.")
        
        # Calcula preço/verifica gratuidade
        resultado_gratuidade = gerenciador.calcular_gratuidade(prato, quantidade_solicitada)
        
        observacao_pedido = descricao or validador.obter_nome_observacao_pedido()
        
        # Commit
        solicitacao_id = db.solicitacao_refeicao.insert(
            solicitante_id=validador.solicitante_real_id,
            is_acompanhante=validador.is_acompanhante,
            prato_id=prato_id,
            preco=resultado_gratuidade['preco_total'],
            quantidade_solicitada=quantidade_solicitada,
            descricao=observacao_pedido,
            status=status
        )
        
        # Atualiza o saldo
        _atualizar_saldo_usuario(validador.solicitante_real_id, resultado_gratuidade['preco_total'])
        
        db.commit()
        return response.json({
            'status': 'success', 
            'message': 'Solicitação de refeição registrada com sucesso!', 
            'solicitacao_id': solicitacao_id
        })
        
    except Exception as e:
        db.rollback()
        return response.json({'status': 'error', 'message': str(e)})


```

#### API de Listagem de Pedidos para a Cozinha

```python
def api_listar_pedidos():
    try:
        # Definir os tipos de usuário
        tipos_normais = ['Paciente', 'Paciente Convenio', 'Acompanhante', 'Hemodialise']
        tipos_filtrados = ['Medico', 'Colaborador', 'Gestor', 'Administrador', 'Instrumentador', 'Colaborador']

        # Obter os IDs dos tipos normais e filtrados
        tipos_normais_ids = [tipo.id for tipo in db(db.user_type.name.belongs(tipos_normais)).select(db.user_type.id)]
        tipos_filtrados_ids = [tipo.id for tipo in db(db.user_type.name.belongs(tipos_filtrados)).select(db.user_type.id)]

        if not tipos_normais_ids or not tipos_filtrados_ids:
            raise ValueError("IDs de tipos de usuário não encontrados.")

        # Obter o ID do setor "Colaborador Hemodialise"
        setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodialise").select(db.setor.id).first()
        setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None

        # 1. Pedidos de tipos de pratos sempre visíveis (A La Carte, Livre e Bebidas)
        pedidos_livres = db(
            (~db.solicitacao_refeicao.status.belongs(['Finalizado', 'Pago']))&
            (db.cardapio.tipo.belongs(['A La Carte', 'Livre', 'Bebidas']))
        ).select(
            db.solicitacao_refeicao.ALL,
            db.cardapio.foto_do_prato,
            db.cardapio.nome,
            db.auth_user.first_name,
            db.auth_user.room,
            db.auth_user.observations,
            db.auth_user.user_type,
            db.setor.name,
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ]
        )

        # 2. Pedidos para tipos normais (qualquer tipo de prato)
        pedidos_normais = db(
            (~db.solicitacao_refeicao.status.belongs(['Finalizado', 'Pago'])) &
            (db.auth_user.user_type.belongs(tipos_normais_ids)) &
            ~((db.auth_user.user_type == db(db.user_type.name == 'Hemodialise').select(db.user_type.id).first().id) &
              (db.auth_user.setor_id == setor_colaborador_hemodialise_id))
        ).select(
            db.solicitacao_refeicao.ALL,
            db.cardapio.foto_do_prato,
            db.cardapio.nome,
            db.auth_user.first_name,
            db.auth_user.room,
            db.auth_user.observations,
            db.auth_user.user_type,
            db.setor.name,
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ]
        )

        # 3. Pedidos para tipos filtrados (somente A La Carte, Livre e Bebidas ou Hemodialise do setor correto)
        pedidos_filtrados = db(
            (~db.solicitacao_refeicao.status.belongs(['Finalizado', 'Pago'])) &
            (db.auth_user.user_type.belongs(tipos_filtrados_ids)) &
            (
                (db.cardapio.tipo.belongs(['A La Carte', 'Livre', 'Bebidas'])) |
                ((db.auth_user.user_type == db(db.user_type.name == 'Hemodialise').select(db.user_type.id).first().id) &
                 (db.auth_user.setor_id == setor_colaborador_hemodialise_id))
            )
        ).select(
            db.solicitacao_refeicao.ALL,
            db.cardapio.foto_do_prato,
            db.cardapio.nome,
            db.auth_user.first_name,
            db.auth_user.room,
            db.auth_user.observations,
            db.auth_user.user_type,
            db.setor.name,
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ]
        )

        # Combinar todas as listas de pedidos
        todos_pedidos = pedidos_livres | pedidos_normais | pedidos_filtrados

        # Acessar `user_type.name` para cada pedido e definir uma prioridade
        for pedido in todos_pedidos:
            user_type_name = pedido.auth_user.user_type.name if pedido.auth_user.user_type else None
            pedido.user_type_name = user_type_name

        # Definir a prioridade de tipos de usuário para ordenação
        prioridade_tipos = {
            'Paciente': 1,
            'Paciente Convenio': 2,
            'Acompanhante': 3
        }

        # Ordenar a lista de pedidos
        pedidos_ordenados = sorted(
            todos_pedidos,
            key=lambda p: (
                prioridade_tipos.get(p.user_type_name, 5),  # Tipos prioritários têm valores menores
                p.solicitacao_refeicao.data_solicitacao  # Ordena por data de solicitação como fallback
            )
        )

        # Formatar os pedidos para JSON
        pedidos_json = [
            {
                'id': pedido.solicitacao_refeicao.id,
                'solicitante': pedido.auth_user.first_name,
                'setor': pedido.setor.name or '-',
                'prato': pedido.cardapio.nome,
                'foto': f"data:image/png;base64,{pedido.cardapio.foto_do_prato}" if pedido.cardapio.foto_do_prato else '',
                'quantidade': pedido.solicitacao_refeicao.quantidade_solicitada,
                'quarto': pedido.auth_user.room or '',
                'observacoes': pedido.auth_user.observations or '',
                'status': pedido.solicitacao_refeicao.status
            }
            for pedido in pedidos_ordenados
        ]

        return response.json({'status': 'success', 'pedidos': pedidos_json})

    except Exception as e:
        import traceback
        error_message = f"Erro ao processar a API: {str(e)}\n{traceback.format_exc()}"
        print(error_message)  # Log para depuração
        return response.json({'status': 'error', 'message': error_message})

```

### 4. Soluções a serem desenvolvidas

## Permitir o agendamento de pratos para o dia corrente

### 1. Fluxo de Agendamento de Pedido (para pedidos fora do horário de disponibilidade)

1. Usuário seleciona um prato de cada tipo (café da manhã, almoço...)
2. Usuário confirma agendamento
3. Sistema registra o pedido com status "Pendente".
4. Sistema confirma o agendamento ao usuário.

### 2. Fluxo de Visualização da Cozinha

1. Cozinha visualiza pedidos por padrão apenas para o dia atual e horário correspondente com a tabela `horario_refeicoes`
2. Processamento normal de pedidos do dia atual

### Exceção para café da manhã

1. O café da manhã após o seu `horário_fim`, poderá ser solicitado gratuitamente (para os que tem direito à gratuidade), no entanto, somente se for agendado para o próximo dia.
2. O sistema edve deixar claro que o prato está agendado e a cozinha deverá visualizá-lo corretamente no próximo dia entre `pedido_fim` e `servido_inicio`.

### Pratos convencionais (todos Exceto A la carte, Livre e Bebidas)

1. Devem desaparecer da listagem do usuário após `pedido_fim` para evitar a solicitação fora do horário.

### Pratos A la carte, Livre e Bebidas

1. Devem sempre aparecer e sempre serem pagos, independente de qualquer regra de negócio.

### **Gratuidade**:
   - Manter as regras de gratuidade existentes

## Considerações Técnicas

- Adicionar transações de banco de dados para garantir consistência
- Implementar validações adequadas para prevenir agendamentos/solicitações inválidos(as)
- Garantir que a interface seja intuitiva para usuários não técnicos e se comuniquem bem com as APIs e controladores desenvolvidos.
- Manter compatibilidade com o sistema débitos existentes (atualmente, cada solicitação de pratos que geram custo, acrescem o valor para o usuário na tabela `user_balance`)
            
         
