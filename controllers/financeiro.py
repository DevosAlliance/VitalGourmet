import json
from gluon import current
from datetime import datetime, timedelta, date
import logging
from decimal import Decimal
import datetime
from io import StringIO
from gluon.contrib.pymysql.err import IntegrityError


@auth.requires(lambda: any(auth.has_membership(role) for role in ['Gestor', 'Administrador']))
def index():
    # Filtro para tipo de usuário
    tipo_usuario = request.vars.tipo_usuario or 'Todos'
    
    if tipo_usuario == 'Paciente':
        tipos = ['Paciente', 'Paciente Convenio', 'Paciente Particular', 'Acompanhante']
    elif tipo_usuario == 'Colaborador':
        tipos = ['Administrador', 'Colaborador', 'Gestor', 'Instrumentador', 'Hemodialise', 'Medico']
    else:  # Todos
        tipos = db(db.user_type.id > 0).select(db.user_type.name).as_list()
        tipos = [tipo['name'] for tipo in tipos]


    # Obter os IDs dos tipos de usuário
    tipo_usuario_ids = [
        tipo.id for tipo in db(db.user_type.name.belongs(tipos)).select(db.user_type.id)
    ]
    
    # Consultar diretamente na tabela user_balance com base no filtro
    query = (db.auth_user.user_type.belongs(tipo_usuario_ids)) & \
            (db.user_balance.user_id == db.auth_user.id) & \
            (db.user_balance.saldo_devedor > 0)

    # Obter usuários com saldo devedor
    usuarios_com_debito = db(query).select(
        db.auth_user.ALL,
        db.user_balance.saldo_devedor
    )
    
    # Calcular saldo total devedor para o filtro atual
    saldo_total = db(query).select(db.user_balance.saldo_devedor.sum()).first()[db.user_balance.saldo_devedor.sum()] or 0

    return dict(usuarios_com_debito=usuarios_com_debito, tipo_usuario=tipo_usuario, saldo_total=saldo_total)

@auth.requires_login()
def ver_solicitacoes_e_saldo():
    paciente_id = request.args(0, cast=int)
    paciente = db.auth_user(paciente_id) or redirect(URL('default', 'listar_pacientes'))

    # Pega o mês selecionado no filtro, ou usa o mês atual como padrão
    mes_selecionado = int(request.vars.mes or request.now.month)
    ano_selecionado = int(request.vars.ano or request.now.year)

    # Filtra as solicitações de refeição do paciente pelo mês e ano selecionado
    solicitacoes = db(
        (db.solicitacao_refeicao.solicitante_id == paciente_id) &
        (db.solicitacao_refeicao.data_solicitacao.month() == mes_selecionado) &
        (db.solicitacao_refeicao.data_solicitacao.year() == ano_selecionado)
    ).select()

    # Obtém o saldo devedor da tabela user_balance
    user_balance = db(db.user_balance.user_id == paciente_id).select(db.user_balance.saldo_devedor).first()
    saldo_devedor = user_balance.saldo_devedor if user_balance else 0  # Retorna 0 se não houver registro

    return dict(
        paciente=paciente,
        solicitacoes=solicitacoes,
        saldo_devedor=saldo_devedor,
        mes_selecionado=mes_selecionado,
        ano_selecionado=ano_selecionado
    )


# pagamentos
@auth.requires_login()
def get_pagamentos():
    paciente_id = request.args(0)
    pagamentos = db(db.pagamentos.paciente_id == paciente_id).select()

    response_data = []
    for pagamento in pagamentos:
        response_data.append({
            'data_pagamento': pagamento.data_pagamento.strftime('%d/%m/%Y'),
            'valor_pago': float(pagamento.valor_pago),
            'descricao': pagamento.descricao or ''
        })

    return response.json({'pagamentos': response_data})


@auth.requires_login()
def adicionar_pagamento():
    if request.env.request_method == 'POST':
        try:
            # Receber dados do POST
            paciente_id = request.args(0)
            valor_pago = Decimal(request.post_vars.valor_pago or 0)  # Converter para Decimal
            descricao = request.post_vars.descricao

            # Validar se o paciente existe
            paciente = db(db.auth_user.id == paciente_id).select().first()
            if not paciente:
                return response.json({'status': 'failed', 'message': 'Paciente não encontrado.'})

            # Inserir o pagamento na tabela de pagamentos
            db.pagamentos.insert(
                paciente_id=paciente_id,
                valor_pago=valor_pago,
                descricao=descricao
            )

            # Atualizar o saldo na tabela user_balance
            saldo_atual = db.user_balance(user_id=paciente_id)
            if saldo_atual:
                # Subtrair o valor pago do saldo existente
                novo_saldo = max(Decimal('0'), saldo_atual.saldo_devedor - valor_pago)
                saldo_atual.update_record(saldo_devedor=novo_saldo)
            else:
                # Criar o registro se não existir
                db.user_balance.insert(user_id=paciente_id, saldo_devedor=max(Decimal('0'), -valor_pago))

            db.commit()

            return response.json({'status': 'success', 'message': 'Pagamento adicionado e saldo atualizado com sucesso.'})
        except Exception as e:
            db.rollback()
            return response.json({'status': 'failed', 'message': str(e)})
    else:
        return response.json({'status': 'failed', 'message': 'Método inválido. Use POST.'})

@auth.requires_login()
def marcar_pagamento_realizado():
    if request.env.request_method == 'POST':
        try:
            import json
            dados = json.loads(request.body.read().decode('utf-8'))
            solicitacoes_ids = dados.get("solicitacoes_ids", [])
            valor_pago = Decimal(dados.get("valor_pago", 0))
            descricao = dados.get("descricao", "")
            forma_pagamento = dados.get("forma_pagamento", "")

            if not solicitacoes_ids or not forma_pagamento:
                raise ValueError("Solicitações ou forma de pagamento inválidas.")

            # Obtém o paciente associado às solicitações
            solicitacoes = db(db.solicitacao_refeicao.id.belongs(solicitacoes_ids)).select()
            if not solicitacoes:
                raise ValueError("Nenhuma solicitação encontrada.")

            paciente_id = solicitacoes.first().solicitante_id

            # Atualiza todas as solicitações selecionadas como pagas e adiciona a forma de pagamento
            db(db.solicitacao_refeicao.id.belongs(solicitacoes_ids)).update(
                foi_pago=True, forma_pagamento=forma_pagamento
            )

            # Atualiza o saldo devedor do paciente
            saldo_atual = db(db.user_balance.user_id == paciente_id).select().first()
            if saldo_atual:
                novo_saldo = max(Decimal('0'), saldo_atual.saldo_devedor - valor_pago)
                saldo_atual.update_record(saldo_devedor=novo_saldo)
            else:
                db.user_balance.insert(user_id=paciente_id, saldo_devedor=max(Decimal('0'), -valor_pago))

            # Registra o pagamento
            pagamento_id = db.pagamentos.insert(
                paciente_id=paciente_id,
                valor_pago=valor_pago,
                descricao=descricao
            )

            # Registra a ação no log do sistema
            db.log_sistema.insert(
                user_id=auth.user.id,
                entidade="pagamentos",
                acao="registro",
                registro_id=pagamento_id,
                observacao=json.dumps({"valor_pago": str(valor_pago), "descricao": descricao, "forma_pagamento": forma_pagamento})
            )

            db.commit()
            return response.json({'status': 'success', 'message': 'Pagamentos registrados e saldo atualizado com sucesso!'})

        except Exception as e:
            db.rollback()
            return response.json({'status': 'error', 'message': str(e)})
    else:
        return response.json({'status': 'error', 'message': 'Método inválido. Use POST.'})

def relatorio_financeiro():
    return dict()

@auth.requires_login()
def api_relatorio_financeiro():
    """
    Retorna um JSON com o resumo financeiro das solicitações de refeições.
    Filtra por mês ou dia corrente e atualiza foi_pago para 'T' se preco <= 0.
    """
    try:
        from datetime import datetime, date, timedelta

        filtro = request.vars.filtro or "mes"

        if filtro == "dia":
            data_inicio = date.today()
            data_fim = date.today()
        else:
            mes_selecionado = date.today().month
            ano_selecionado = date.today().year
            data_inicio = date(ano_selecionado, mes_selecionado, 1)
            proximo_mes = data_inicio.replace(day=28) + timedelta(days=4)
            data_fim = proximo_mes - timedelta(days=proximo_mes.day)

        # Atualiza automaticamente os pedidos onde preco <= 0
        db((db.solicitacao_refeicao.preco <= 0)).update(
            foi_pago='T', 
            forma_pagamento='Gratuidade'
        )
        db.commit()

        # Filtra registros no intervalo
        solicitacoes = db(
            (db.solicitacao_refeicao.data_solicitacao >= data_inicio) &
            (db.solicitacao_refeicao.data_solicitacao <= data_fim)
        ).select(
            db.solicitacao_refeicao.ALL,
            db.auth_user.first_name,
            db.auth_user.user_type,
            db.cardapio.nome,
            db.auth_user.id,
            left=[
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id)
            ]
        )

        pedidos_resumo = []
        total_a_receber = 0  

        for solicitacao in solicitacoes:
            valor = float(solicitacao.solicitacao_refeicao.preco or 0)
            
            if valor > 0:
                total_a_receber += valor  # Somar apenas os valores reais

            pedidos_resumo.append({
                "Data": solicitacao.solicitacao_refeicao.data_solicitacao.strftime('%d/%m/%Y'),
                "ID": solicitacao.auth_user.id,
                "Tipo de Usuário": solicitacao.auth_user.user_type.name or "Desconhecido",
                "Solicitante": solicitacao.auth_user.first_name or "Não encontrado",
                "Prato": solicitacao.cardapio.nome or "Não informado",
                "Forma de Pagamento": solicitacao.solicitacao_refeicao.forma_pagamento or "Não especificado",
                "Valor": valor,
            })

        return response.json({
            "status": "success",
            "pedidos": pedidos_resumo,
            "total_a_receber": round(total_a_receber, 2)
        })

    except Exception as e:
        print("Erro na API:", e)
        return response.json({"status": "error", "message": str(e)})


@auth.requires_login()
def api_listar_pagamentos():
    """
    API para listar pagamentos de um paciente específico
    """
    try:
        paciente_id = request.args(0)
        
        if not paciente_id:
            raise ValueError("ID do paciente não fornecido.")
        
        # Verificar se o paciente existe
        paciente = db.auth_user(paciente_id)
        if not paciente:
            raise ValueError("Paciente não encontrado.")
        
        # Buscar pagamentos do paciente
        pagamentos = db(db.pagamentos.paciente_id == paciente_id).select(
            orderby=~db.pagamentos.data_pagamento  # Mais recentes primeiro
        )
        
        # Formaterar dados para JSON
        pagamentos_json = []
        for pagamento in pagamentos:
            pagamentos_json.append({
                'id': pagamento.id,
                'valor_pago': float(pagamento.valor_pago),
                'data_pagamento': pagamento.data_pagamento.strftime('%d/%m/%Y'),
                'descricao': pagamento.descricao or 'Sem descrição'
            })
        
        return response.json({
            'status': 'success',
            'pagamentos': pagamentos_json,
            'total': len(pagamentos_json)
        })
        
    except Exception as e:
        return response.json({
            'status': 'error',
            'message': str(e)
        })



