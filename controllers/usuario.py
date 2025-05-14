import json
from gluon import current
from datetime import datetime, timedelta, date
import logging
from decimal import Decimal
from io import StringIO
from gluon.contrib.pymysql.err import IntegrityError




# models/regras_gratuidade.py
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


# controllers/api.py
def api_registrar_solicitacao_refeicao():
    if request.env.request_method != 'POST':
        return response.json({'status': 'error', 'message': 'Método inválido. Use POST.'})
    
    try:
        solicitante_id = request.post_vars.get('solicitante_id') or (auth.user.id if auth.user else None)
        dados = json.loads(request.body.read().decode('utf-8'))
        
        # Validação básica dos dados
        prato_id = int(dados.get('pratoid'))
        quantidade_solicitada = int(dados.get('quantidade'))
        descricao = dados.get('descricao', None)
        status = dados.get('status', 'Pendente')

        hoje = datetime.now()

        # Verifica se o prato existe
        prato = db(db.cardapio.id == prato_id).select(
            db.cardapio.ALL,
            db.horario_refeicoes.pedido_fim,
            left=[
                db.horario_refeicoes.on(db.cardapio.tipo == db.horario_refeicoes.refeicao)
            ]
        ).first()

        if not prato:
            raise ValueError("O prato especificado não existe.")

        # Inicializa classes de validação e gratuidade
        validador = ValidadorUsuario(solicitante_id, db)
        gerenciador = GerenciadorGratuidade(validador, db)

        # Verifica se o usuário pode solicitar o prato
        if not validador.pode_solicitar_prato(prato.cardapio):
            raise ValueError("Você não tem permissão para solicitar este prato.")

        # Calcula preço/verifica gratuidade
        resultado_gratuidade = gerenciador.calcular_gratuidade(prato.cardapio, quantidade_solicitada)

        observacao_pedido = descricao or validador.obter_nome_observacao_pedido()

        dict_solicitacao = {
            'solicitante_id': validador.solicitante_real_id,
            'is_acompanhante': validador.is_acompanhante,
            'prato_id': prato_id,
            'preco': resultado_gratuidade['preco_total'],
            'quantidade_solicitada': quantidade_solicitada,
            'descricao': observacao_pedido,
            'status': status
        }

        if prato.cardapio.tipo == 'Café da Manhã' and\
            prato.horario_refeicoes.pedido_fim < hoje.time():
            dict_solicitacao['data_solicitacao'] = (hoje + timedelta(days=1)).date()

        # Commit
        solicitacao_id = db.solicitacao_refeicao.insert(**dict_solicitacao)

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


def _atualizar_saldo_usuario(usuario_id, valor_adicional):
    """Função auxiliar para atualizar o saldo do usuário"""
    saldo_atual = db(db.user_balance.user_id == usuario_id).select().first()
    
    if saldo_atual:
        novo_saldo = saldo_atual.saldo_devedor + valor_adicional
        saldo_atual.update_record(saldo_devedor=novo_saldo)
    else:
        db.user_balance.insert(user_id=usuario_id, saldo_devedor=valor_adicional)

def _converter_dia_semana(dia_ingles):
    """Função auxiliar para converter o dia da semana para português"""
    dias_semana = {
        'Monday': 'Segunda-feira',
        'Tuesday': 'Terca-feira',
        'Wednesday': 'Quarta-feira',
        'Thursday': 'Quinta-feira',
        'Friday': 'Sexta-feira',
        'Saturday': 'Sabado',
        'Sunday': 'Domingo'
    }
    return dias_semana.get(dia_ingles, dia_ingles)


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
        hoje = datetime.now()
        amanha = _converter_dia_semana((hoje + timedelta(days=1)).strftime('%A'))
        dia_semana = _converter_dia_semana(hoje.strftime('%A'))
        # pratos permitidos para o usuário
        pratos_permitidos = db(
            (db.cardapio.tipos_usuario.contains(validador.user_type_name)) &
            (db.cardapio.dias_semana.contains(dia_semana)) &
            (db.cardapio.tipo == db.horario_refeicoes.refeicao)
        ).select(orderby=db.horario_refeicoes.pedido_fim)
        hora_fim_cafe_manha = db(db.horario_refeicoes.refeicao == 'Café da Manhã').select()[0].pedido_fim
        if hora_fim_cafe_manha <= hoje.time():
            cafe_manha_dia_seguinte = db(
                (db.cardapio.tipos_usuario.contains(validador.user_type_name)) &
                (db.cardapio.dias_semana.contains(amanha)) &
                (db.cardapio.tipo == 'Café da Manhã') &
                (db.cardapio.tipo == db.horario_refeicoes.refeicao)
            ).select()
            pratos_permitidos = cafe_manha_dia_seguinte | pratos_permitidos
        pratos_json = {}
        
        # Dicionário para rastrear pratos já processados por tipo
        pratos_processados = {}
        
        for prato in pratos_permitidos:
            # filtra por horario apenas os items do dia atual(Café da manhã pode incluir items do dia seguinte)
            if prato.horario_refeicoes.pedido_fim:
                if (
                    not (prato.cardapio.tipo == 'Café da Manhã') or
                    (
                        prato.cardapio.tipo == 'Café da Manhã' and 
                        amanha not in prato.cardapio.dias_semana
                    )
                ):
                    hora_fim = prato.horario_refeicoes.pedido_fim
                    if hora_fim <= hoje.time():
                        continue
                        
            # Inicializa a lista para o tipo se não existir
            if not pratos_json.get(prato.cardapio.tipo):
                pratos_json[prato.cardapio.tipo] = []
                pratos_processados[prato.cardapio.tipo] = set()
                
            # Verifica se este prato já foi processado (evitar repetições)
            if prato.cardapio.id in pratos_processados[prato.cardapio.tipo]:
                continue
                
            # Marca como processado
            pratos_processados[prato.cardapio.tipo].add(prato.cardapio.id)
            
            # Calcula a gratuidade e preço para o prato
            resultado_gratuidade = gerenciador.calcular_gratuidade(prato.cardapio)
            
            pratos_json[prato.cardapio.tipo].append({
                'id': prato.cardapio.id,
                'nome': prato.cardapio.nome,
                'descricao': prato.cardapio.descricao,
                'ingredientes': prato.cardapio.ingredientes,
                'tipos_usuario': prato.cardapio.tipos_usuario,
                'dias_semana': prato.cardapio.dias_semana,
                'foto_do_prato': prato.cardapio.foto_do_prato,
                'preco': float(resultado_gratuidade['preco_total']),
                'gratuidade': resultado_gratuidade['gratuidade'],
                'motivo_gratuidade': resultado_gratuidade['motivo_gratuidade']
            })
        
        # Ordena cada categoria de prato por gratuidade (gratuitos primeiro)
        for tipo_refeicao in pratos_json:
            pratos_json[tipo_refeicao] = sorted(
                pratos_json[tipo_refeicao],
                key=lambda x: (0 if x['gratuidade'] else 1, x['nome'])  # Ordena por gratuidade (True primeiro) e depois por nome
            )
        
        # Define a ordem correta das refeições
        ordem_refeicoes = ['Café da Manhã', 'Almoço', 'Jantar', 'Ceia']
        
        # Cria um novo dicionário ordenado com as refeições na ordem correta
        pratos_ordenados = {}
        for refeicao in ordem_refeicoes:
            if refeicao in pratos_json:
                pratos_ordenados[refeicao] = pratos_json[refeicao]
        
        # Adiciona qualquer outra refeição que não esteja na ordem predefinida
        for refeicao in pratos_json:
            if refeicao not in pratos_ordenados:
                pratos_ordenados[refeicao] = pratos_json[refeicao]
        
        return response.json({
            'status': 'success',
            'tipo_usuario': validador.user_type_name,
            'pratos': pratos_ordenados
        })
        
    except Exception as e:
        print(f"Erro na API listar pratos: {str(e)}")
        return response.json({'status': 'error', 'message': str(e)})


def _obter_horarios_prato(tipo_refeicao, tipo_usuario):
    """Função auxiliar para obter os horários de pedido para um prato"""
    horarios = db(
        (db.horario_refeicoes.refeicao == tipo_refeicao) &
        (db.horario_refeicoes.tipo_usuario.contains(tipo_usuario))
    ).select().first()
    
    return {
        'inicio': str(horarios.pedido_inicio) if horarios and horarios.pedido_inicio else None,
        'fim': str(horarios.pedido_fim) if horarios and horarios.pedido_fim else None
    }


# Inserir configurações padrão (executar apenas uma vez)
def inicializar_configuracoes_padrao():
    configuracoes = [
        {
            'nome': 'idade_minima_gratuidade',
            'valor': '17',
            'descricao': 'Idade mínima para gratuidade de acompanhante de paciente convênio',
            'tipo': 'int'
        },
        {
            'nome': 'idade_maxima_gratuidade',
            'valor': '60',
            'descricao': 'Idade máxima para gratuidade de acompanhante de paciente convênio',
            'tipo': 'int'
        },
        {
            'nome': 'tipos_usuario_gratuidade_ilimitada',
            'valor': json.dumps(['Colaborador', 'Medico', 'Hemodialise', 'Instrumentador', 'Administrador', 'Gestor']),
            'descricao': 'Tipos de usuário com gratuidade ilimitada',
            'tipo': 'json'
        },
        {
            'nome': 'tipos_usuario_gratuidade_primeiro_prato',
            'valor': json.dumps(['Paciente Convenio', 'Paciente']),
            'descricao': 'Tipos de usuário com gratuidade no primeiro prato',
            'tipo': 'json'
        },
        {
            'nome': 'tipos_prato_sem_gratuidade',
            'valor': json.dumps(['A la carte', 'Livre', 'Bebidas']),
            'descricao': 'Tipos de prato que não têm gratuidade',
            'tipo': 'json'
        },
        {
            'nome': 'tipos_paciente_acompanhante_herda_gratuidade',
            'valor': json.dumps(['Paciente Convenio']),
            'descricao': 'Tipos de paciente onde o acompanhante herda gratuidade (se paciente está na faixa etária especial)',
            'tipo': 'json'
        },
        {
            'nome': 'acompanhante_herda_todos_pratos_gratuidade',
            'valor': 'false',
            'descricao': 'Se verdadeiro, acompanhante herda gratuidade para todos os pratos; se falso, apenas para o primeiro',
            'tipo': 'boolean'
        }
    ]
    
    for config in configuracoes:
        if not db(db.configuracoes.nome == config['nome']).select().first():
            db.configuracoes.insert(**config)
            db.commit()

#  meus pedidos
@auth.requires_login()
def meus_pedidos():

    """
    Exibe as solicitações de refeições feitas pelo usuário logado.
    """
    # Obtém o ID do usuário logado
    solicitante_id = auth.user.id

    # Consulta para buscar as solicitações que não estão finalizadas
    pedidos = db((db.solicitacao_refeicao.solicitante_id == solicitante_id)).select(
        db.solicitacao_refeicao.ALL,
        db.cardapio.nome,
        join=db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id)
    )

    return dict(pedidos=pedidos)


@auth.requires_login()
def perfil():
    """
    Permite que o usuário visualize e altere seus detalhes de perfil
    """
    # Obter o usuário logado
    user = db.auth_user(auth.user.id)

    # Formulário para edição dos dados do usuário
    form = SQLFORM(db.auth_user, user,
                   fields=['first_name', 'last_name', 'email', 'password'],
                   showid=False)

    # Processar o formulário
    if form.process(onvalidation=valida_perfil).accepted:
        response.flash = 'Perfil atualizado com sucesso!'
    elif form.errors:
        response.flash = 'Erro ao atualizar o perfil. Verifique os dados.'

    return dict(form=form)

def valida_perfil(form):
    """
    Validação adicional para garantir consistência nos campos (ex. força da senha)
    """
    if form.vars.password and len(form.vars.password) < 6:
        form.errors.password = 'A senha deve ter pelo menos 6 caracteres.'
