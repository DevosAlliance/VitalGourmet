import json
from gluon import current
from datetime import datetime, timedelta, date
import logging
from decimal import Decimal
import datetime
from io import StringIO
from gluon.contrib.pymysql.err import IntegrityError

def api_registrar_solicitacao_refeicao():
    if request.env.request_method == 'POST':
        try:
            solicitante_id = request.post_vars.get('solicitante_id') or (auth.user.id if auth.user else None)
            dados = request.post_vars

            prato_id = int(dados.get('pratoid'))
            quantidade_solicitada = int(dados.get('quantidade'))
            descricao = dados.get('descricao', None)
            status = dados.get('status', 'Pendente')

            # Verifica se o prato existe
            prato = db(db.cardapio.id == prato_id).select().first()
            if not prato:
                raise ValueError("O prato especificado não existe.")

            # Obtém os dados do usuário solicitante
            user = db.auth_user(solicitante_id)
            user_type_name = db.user_type[user.user_type].name if user.user_type else 'Visitante'

            hoje = request.now.date()
            preco_total = prato.preco * quantidade_solicitada

            # **Inicializa variáveis**
            is_acompanhante = ''
            solicitante_real = solicitante_id
            observacao_pedido = descricao or ""

            # **Verifica se o solicitante é um acompanhante**
            acompanhante_vinculo = db(db.acompanhante_vinculo.acompanhante_id == solicitante_id).select().first()

            if acompanhante_vinculo:
                paciente_vinculado = db.auth_user(acompanhante_vinculo.paciente_id)
                if paciente_vinculado:
                    is_acompanhante = 1
                    solicitante_real = paciente_vinculado.id
                    observacao_pedido = f"Pedido de acompanhante: {user.first_name}"

            # **Verifica pedidos anteriores para determinar gratuidade**
            pedidos_paciente = db(
                (db.solicitacao_refeicao.solicitante_id == solicitante_real) &
                (db.solicitacao_refeicao.prato_id == prato_id) &
                (db.solicitacao_refeicao.data_solicitacao == hoje)
            ).select()

            pedido_paciente_gratis = pedidos_paciente.find(lambda p: not p.is_acompanhante and p.preco == 0)
            pedido_acompanhante_gratis = pedidos_paciente.find(lambda p: p.is_acompanhante and p.preco == 0)

            # **Regras de Gratuidade**
            if prato.tipo not in ['A la carte', 'Livre', 'Bebidas']:
                if user_type_name in ['Colaborador', 'Medico', 'Hemodialise', 'Instrumentador', 'Gestor', 'Administrador']:
                    preco_total = 0
                elif user_type_name in ['Paciente Convenio', 'Paciente']:
                    if not pedido_paciente_gratis:
                        preco_total = 0
                elif is_acompanhante:
                    if paciente_vinculado and paciente_vinculado.user_type == db(db.user_type.name == 'Paciente Convenio').select().first().id:
                        idade_paciente = (hoje - paciente_vinculado.birth_date).days // 365
                        if idade_paciente > 70 and not pedido_acompanhante_gratis:
                            preco_total = 0

            # **Verifica se o tipo de usuário pode solicitar o prato**
            tipos_usuario_prato = (
                json.loads(prato.tipos_usuario) if isinstance(prato.tipos_usuario, str)
                else prato.tipos_usuario
            )

            if user_type_name not in tipos_usuario_prato:
                raise ValueError("Você não tem permissão para solicitar este prato.")

            # **Registra a solicitação no banco de dados**
            solicitacao_id = db.solicitacao_refeicao.insert(
                solicitante_id=solicitante_real,
                is_acompanhante=is_acompanhante,  # **AGORA ISSO FUNCIONA PERFEITAMENTE 🚀**
                prato_id=prato_id,
                preco=preco_total,
                quantidade_solicitada=quantidade_solicitada,
                descricao=observacao_pedido,
                status=status
            )

            # **Atualiza o saldo do paciente vinculado**
            saldo_atual = db(db.user_balance.user_id == solicitante_real).select().first()
            if saldo_atual:
                novo_saldo = saldo_atual.saldo_devedor + preco_total
                saldo_atual.update_record(saldo_devedor=novo_saldo)
            else:
                db.user_balance.insert(user_id=solicitante_real, saldo_devedor=preco_total)

            db.commit()
            return response.json({'status': 'success', 'message': 'Solicitação de refeição registrada com sucesso!', 'solicitacao_id': solicitacao_id})
            response.flash = f"Erro ao atualizar o horário:"


        except Exception as e:
            db.rollback()
            return response.json({'status': 'error', 'message': str(e)})
    else:
        return response.json({'status': 'error', 'message': 'Método inválido. Use POST.'})





def api_listar_pratos_para_usuario():
    try:
        solicitante_id = request.vars.get('solicitante_id') or \
                         (request.args(0) if len(request.args) > 0 else None) or \
                         (auth.user.id if auth.user else None)

        if not solicitante_id:
            raise ValueError("ID do solicitante não fornecido.")

        # Busca o solicitante e define informações básicas
        user_query = db.auth_user(solicitante_id)
        user = user_query
        user_type_id = user.user_type
        user_type_name = db.user_type[user_type_id].name if user_type_id else 'Visitante'

        dia_atual = datetime.datetime.now().strftime('%A')
        dias_semana = {
            'Monday': 'Segunda-feira',
            'Tuesday': 'Terca-feira',
            'Wednesday': 'Quarta-feira',
            'Thursday': 'Quinta-feira',
            'Friday': 'Sexta-feira',
            'Saturday': 'Sabado',
            'Sunday': 'Domingo'
        }
        dia_atual = dias_semana[dia_atual]

        pratos_permitidos = db(
            (db.cardapio.tipos_usuario.contains(user_type_name)) &
            (db.cardapio.dias_semana.contains(dia_atual))
        ).select()

        ingredientes_necessarios = {
            ing['nome'].lower()
            for prato in pratos_permitidos
            for ing in prato.ingredientes or []
        }

        estoques = db(db.estoque.nome.lower().belongs(ingredientes_necessarios)).select()
        estoque_dict = {estoque.nome.lower(): int(estoque.gramatura) for estoque in estoques}

        pratos_json = []

        for prato in pratos_permitidos:
            horarios = db(
                (db.horario_refeicoes.refeicao == prato.tipo) &
                (db.horario_refeicoes.tipo_usuario.contains(user_type_name))
            ).select().first()

            pedido_inicio = str(horarios.pedido_inicio) if horarios and horarios.pedido_inicio else None
            pedido_fim = str(horarios.pedido_fim) if horarios and horarios.pedido_fim else None

            estoque_disponivel = True
            if prato.ingredientes:
                for ingrediente in prato.ingredientes:
                    nome_ingrediente = ingrediente.get('nome', '').lower()
                    gramatura_necessaria = int(ingrediente.get('gramatura', 0))
                    estoque_gramatura = int(estoque_dict.get(nome_ingrediente, 0))

                    if estoque_gramatura < gramatura_necessaria:
                        estoque_disponivel = False
                        break

            preco_total = prato.preco
            gratuidade = False
            motivo_gratuidade = None

            if prato.tipo not in ['A la carte', 'Livre', 'Bebidas']:
                if user_type_name in ['Colaborador', 'Medico', 'Hemodialise', 'Instrumentador', 'Gestor', 'Administrador']:
                    gratuidade = True
                    motivo_gratuidade = 'Gratuidade ilimitada para médicos e colaboradores'
                    preco_total = 0

                elif user_type_name in ['Paciente Convenio', 'Paciente']:
                    pedido_existente = db(
                        (db.solicitacao_refeicao.solicitante_id == solicitante_id) &
                        (db.solicitacao_refeicao.data_solicitacao == request.now.date()) &
                        (db.solicitacao_refeicao.prato_id == prato.id)
                    ).select().first()

                    if not pedido_existente:
                        gratuidade = True
                        motivo_gratuidade = 'Primeiro prato do dia gratuito'
                        preco_total = 0

                elif user_type_name == 'Acompanhante':
                    acompanhante_vinculo = db(db.acompanhante_vinculo.acompanhante_id == solicitante_id).select().first()
                    if acompanhante_vinculo:
                        paciente_vinculado = db.auth_user(acompanhante_vinculo.paciente_id)
                        if paciente_vinculado.user_type == db(db.user_type.name == 'Paciente Convenio').select().first().id:
                            idade_paciente = (request.now.date() - paciente_vinculado.birth_date).days // 365
                            if idade_paciente > 70:
                                pedido_existente = db(
                                    (db.solicitacao_refeicao.solicitante_id == solicitante_id) &
                                    (db.solicitacao_refeicao.data_solicitacao == request.now.date()) &
                                    (db.solicitacao_refeicao.prato_id == prato.id)
                                ).select().first()

                                if not pedido_existente:
                                    gratuidade = True
                                    motivo_gratuidade = 'Gratuidade devido ao paciente vinculado (> 70 anos)'
                                    preco_total = 0

            pratos_json.append({
                'id': prato.id,
                'nome': prato.nome,
                'descricao': prato.descricao,
                'tipo': prato.tipo,
                'ingredientes': prato.ingredientes,
                'tipos_usuario': prato.tipos_usuario,
                'dias_semana': prato.dias_semana,
                'foto_do_prato': prato.foto_do_prato,
                'preco': float(preco_total),
                'pedido_inicio': pedido_inicio,
                'pedido_fim': pedido_fim,
                'gratuidade': gratuidade,
                'motivo_gratuidade': motivo_gratuidade
            })

        pratos_json.sort(key=lambda prato: (prato['tipo'] == 'Bebidas', prato['nome']))

        return response.json({
            'status': 'success',
            'tipo_usuario': user_type_name,
            'pratos': pratos_json
        })

    except Exception as e:
        print(f"Erro na API listar pratos: {str(e)}")
        return response.json({'status': 'error', 'message': str(e)})





def atualizar_saldos():
    # Consulta todos os usuários que possuem tipos definidos
    usuarios = db(db.auth_user).select()

    for usuario in usuarios:
        # Calcular o saldo do usuário (a lógica de calcular_saldo_devedor deve estar implementada)
        saldo_devedor = calcular_saldo_devedor(usuario.id)

        # Atualizar ou inserir o saldo na tabela user_balance
        db.user_balance.update_or_insert(
            db.user_balance.user_id == usuario.id,
            user_id=usuario.id,
            saldo_devedor=saldo_devedor
        )

def calcular_saldo_devedor(paciente_id):
    # Total de pagamentos realizados pelo paciente
    total_pagamentos = db.pagamentos.valor_pago.sum()
    total_pago = db(db.pagamentos.paciente_id == paciente_id).select(total_pagamentos).first()[total_pagamentos] or 0

    # Total de valores das solicitações de refeição do paciente
    total_solicitacoes = db.solicitacao_refeicao.preco.sum()
    total_valor_solicitacoes = db(db.solicitacao_refeicao.solicitante_id == paciente_id).select(total_solicitacoes).first()[total_solicitacoes] or 0

    # Saldo devedor é a diferença entre o total de solicitações e o total pago
    saldo_devedor = total_valor_solicitacoes - total_pago

    return saldo_devedor

#  meus pedidos
@auth.requires_login()
@cache.action(time_expire=300, cache_model=cache.ram, session=True, vars=False, lang=False, user_agent=False, public=False)
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


