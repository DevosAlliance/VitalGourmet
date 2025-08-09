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


@auth.requires_login()
def api_todos_pedidos_paciente():
    """
    API SIMPLES para buscar TODOS os pedidos de um paciente
    Sem filtro de período - mostra TUDO de uma vez
    """
    try:
        paciente_id = request.args(0, cast=int)
        
        if not paciente_id:
            raise ValueError("ID do paciente não fornecido.")
        
        # Verificar se o paciente existe
        paciente = db.auth_user(paciente_id)
        if not paciente:
            raise ValueError("Paciente não encontrado.")
        
        # Buscar TODAS as solicitações do paciente (SEM FILTRO DE PERÍODO)
        solicitacoes = db(
            db.solicitacao_refeicao.solicitante_id == paciente_id
        ).select(
            db.solicitacao_refeicao.ALL,
            db.cardapio.nome,
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id)
            ],
            orderby=~db.solicitacao_refeicao.data_solicitacao  # Mais recentes primeiro
        )
        
        # Formatar dados para JSON de forma simples
        pedidos_json = []
        for sol in solicitacoes:
            pedidos_json.append({
                'id': sol.solicitacao_refeicao.id,
                'prato_nome': sol.cardapio.nome,
                'quantidade_solicitada': sol.solicitacao_refeicao.quantidade_solicitada,
                'preco': float(sol.solicitacao_refeicao.preco),
                'data_solicitacao': sol.solicitacao_refeicao.data_solicitacao.strftime('%Y-%m-%d'),
                'status': sol.solicitacao_refeicao.status,
                'foi_pago': bool(sol.solicitacao_refeicao.foi_pago),
                'forma_pagamento': sol.solicitacao_refeicao.forma_pagamento or '',
                'descricao': sol.solicitacao_refeicao.descricao or ''
            })
        
        return response.json({
            'status': 'success',
            'pedidos': pedidos_json,
            'total': len(pedidos_json)
        })
        
    except Exception as e:
        import traceback
        error_msg = f"Erro: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)  # Para debug
        return response.json({
            'status': 'error',
            'message': str(e)
        })
    

@auth.requires_login()
def ver_solicitacoes_e_saldo():
    """
    Controlador principal SIMPLIFICADO
    Apenas carrega a página - os dados vêm via API
    """
    paciente_id = request.args(0, cast=int)
    paciente = db.auth_user(paciente_id) or redirect(URL('default', 'listar_pacientes'))

    # Não precisa mais filtrar por mês/ano aqui
    # A nova interface carrega tudo via JavaScript
    
    return dict(
        paciente=paciente
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



# Adicionar estas funções ao seu controlador financeiro

@auth.requires_login()
def api_todas_solicitacoes():
    """
    API para buscar TODAS as solicitações de um paciente, independente do período
    Otimizada para a nova interface financeira
    """
    try:
        paciente_id = request.args(0, cast=int)
        
        if not paciente_id:
            raise ValueError("ID do paciente não fornecido.")
        
        # Verificar se o paciente existe
        paciente = db.auth_user(paciente_id)
        if not paciente:
            raise ValueError("Paciente não encontrado.")
        
        # Buscar TODAS as solicitações do paciente (sem filtro de período)
        solicitacoes = db(
            db.solicitacao_refeicao.solicitante_id == paciente_id
        ).select(
            db.solicitacao_refeicao.ALL,
            db.cardapio.nome,
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id)
            ],
            orderby=~db.solicitacao_refeicao.data_solicitacao  # Mais recentes primeiro
        )
        
        # Formatar dados para JSON
        solicitacoes_json = []
        for solicitacao in solicitacoes:
            solicitacoes_json.append({
                'id': solicitacao.solicitacao_refeicao.id,
                'prato_nome': solicitacao.cardapio.nome,
                'quantidade_solicitada': solicitacao.solicitacao_refeicao.quantidade_solicitada,
                'preco': float(solicitacao.solicitacao_refeicao.preco),
                'data_solicitacao': solicitacao.solicitacao_refeicao.data_solicitacao.isoformat(),
                'status': solicitacao.solicitacao_refeicao.status,
                'foi_pago': solicitacao.solicitacao_refeicao.foi_pago or False,
                'forma_pagamento': solicitacao.solicitacao_refeicao.forma_pagamento,
                'descricao': solicitacao.solicitacao_refeicao.descricao or ''
            })
        
        # Calcular estatísticas
        total_pendente = sum(s['preco'] for s in solicitacoes_json if not s['foi_pago'] and s['preco'] > 0)
        total_pago = sum(s['preco'] for s in solicitacoes_json if s['foi_pago'])
        qtd_pendentes = len([s for s in solicitacoes_json if not s['foi_pago'] and s['preco'] > 0])
        qtd_pagos = len([s for s in solicitacoes_json if s['foi_pago']])
        qtd_gratuitos = len([s for s in solicitacoes_json if s['preco'] == 0])
        
        return response.json({
            'status': 'success',
            'solicitacoes': solicitacoes_json,
            'estatisticas': {
                'total_pendente': total_pendente,
                'total_pago': total_pago,
                'qtd_pendentes': qtd_pendentes,
                'qtd_pagos': qtd_pagos,
                'qtd_gratuitos': qtd_gratuitos,
                'total_itens': len(solicitacoes_json)
            }
        })
        
    except Exception as e:
        import traceback
        error_msg = f"Erro ao buscar solicitações: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)  # Log para debug
        return response.json({
            'status': 'error',
            'message': str(e)
        })


@auth.requires_login()
def api_resumo_financeiro():
    """
    API para buscar resumo financeiro rápido (sem detalhes das solicitações)
    Útil para dashboards e visões gerais
    """
    try:
        paciente_id = request.args(0, cast=int)
        
        if not paciente_id:
            raise ValueError("ID do paciente não fornecido.")
        
        # Buscar saldo atual
        user_balance = db(db.user_balance.user_id == paciente_id).select().first()
        saldo_devedor = float(user_balance.saldo_devedor) if user_balance else 0.0
        
        # Contar solicitações por status
        query_base = db.solicitacao_refeicao.solicitante_id == paciente_id
        
        total_pendentes = db(query_base & (db.solicitacao_refeicao.foi_pago == False) & 
                           (db.solicitacao_refeicao.preco > 0)).count()
        
        total_pagos = db(query_base & (db.solicitacao_refeicao.foi_pago == True)).count()
        
        total_gratuitos = db(query_base & (db.solicitacao_refeicao.preco == 0)).count()
        
        # Valor total pendente e pago
        pendentes = db(query_base & (db.solicitacao_refeicao.foi_pago == False) & 
                      (db.solicitacao_refeicao.preco > 0)).select(
                          db.solicitacao_refeicao.preco.sum().with_alias('total')
                      ).first()
        valor_pendente = float(pendentes.total or 0)
        
        pagos = db(query_base & (db.solicitacao_refeicao.foi_pago == True)).select(
                   db.solicitacao_refeicao.preco.sum().with_alias('total')
               ).first()
        valor_pago = float(pagos.total or 0)
        
        # Últimos pagamentos
        ultimos_pagamentos = db(db.pagamentos.paciente_id == paciente_id).select(
            orderby=~db.pagamentos.data_pagamento,
            limitby=(0, 5)
        )
        
        pagamentos_json = []
        for pagamento in ultimos_pagamentos:
            pagamentos_json.append({
                'data': pagamento.data_pagamento.strftime('%d/%m/%Y'),
                'valor': float(pagamento.valor_pago),
                'descricao': pagamento.descricao or 'Sem descrição'
            })
        
        return response.json({
            'status': 'success',
            'resumo': {
                'saldo_devedor': saldo_devedor,
                'valor_pendente': valor_pendente,
                'valor_pago': valor_pago,
                'qtd_pendentes': total_pendentes,
                'qtd_pagos': total_pagos,
                'qtd_gratuitos': total_gratuitos,
                'ultimos_pagamentos': pagamentos_json
            }
        })
        
    except Exception as e:
        return response.json({
            'status': 'error',
            'message': str(e)
        })


@auth.requires_login()
def api_estatisticas_periodo():
    """
    API para buscar estatísticas por período específico
    """
    try:
        paciente_id = request.args(0, cast=int)
        periodo = request.vars.periodo or 'mes_atual'  # mes_atual, mes_anterior, ultimo_3_meses, etc.
        
        if not paciente_id:
            raise ValueError("ID do paciente não fornecido.")
        
        # Calcular datas baseado no período
        hoje = datetime.now().date()
        
        if periodo == 'mes_atual':
            inicio = hoje.replace(day=1)
            fim = hoje
        elif periodo == 'mes_anterior':
            primeiro_dia_mes_atual = hoje.replace(day=1)
            ultimo_dia_mes_anterior = primeiro_dia_mes_atual - timedelta(days=1)
            inicio = ultimo_dia_mes_anterior.replace(day=1)
            fim = ultimo_dia_mes_anterior
        elif periodo == 'ultimo_3_meses':
            inicio = (hoje.replace(day=1) - timedelta(days=90))
            fim = hoje
        elif periodo == 'ano_atual':
            inicio = hoje.replace(month=1, day=1)
            fim = hoje
        else:
            # Se não especificado, usar todos os dados
            inicio = None
            fim = None
        
        # Construir query
        query = db.solicitacao_refeicao.solicitante_id == paciente_id
        
        if inicio and fim:
            query &= (db.solicitacao_refeicao.data_solicitacao >= inicio) & \
                     (db.solicitacao_refeicao.data_solicitacao <= fim)
        
        # Buscar dados do período
        solicitacoes = db(query).select()
        
        # Processar estatísticas
        stats = {
            'total_itens': len(solicitacoes),
            'valor_total': 0,
            'valor_pago': 0,
            'valor_pendente': 0,
            'itens_pagos': 0,
            'itens_pendentes': 0,
            'itens_gratuitos': 0,
            'por_dia': {},
            'por_status': {}
        }
        
        for solicitacao in solicitacoes:
            valor = float(solicitacao.preco)
            data_str = solicitacao.data_solicitacao.strftime('%Y-%m-%d')
            
            # Totais gerais
            stats['valor_total'] += valor
            
            if solicitacao.foi_pago:
                stats['valor_pago'] += valor
                stats['itens_pagos'] += 1
            elif valor > 0:
                stats['valor_pendente'] += valor
                stats['itens_pendentes'] += 1
            else:
                stats['itens_gratuitos'] += 1
            
            # Por dia
            if data_str not in stats['por_dia']:
                stats['por_dia'][data_str] = {'valor': 0, 'quantidade': 0}
            stats['por_dia'][data_str]['valor'] += valor
            stats['por_dia'][data_str]['quantidade'] += 1
            
            # Por status
            status = solicitacao.status
            if status not in stats['por_status']:
                stats['por_status'][status] = {'valor': 0, 'quantidade': 0}
            stats['por_status'][status]['valor'] += valor
            stats['por_status'][status]['quantidade'] += 1
        
        return response.json({
            'status': 'success',
            'periodo': periodo,
            'inicio': inicio.isoformat() if inicio else None,
            'fim': fim.isoformat() if fim else None,
            'estatisticas': stats
        })
        
    except Exception as e:
        return response.json({
            'status': 'error',
            'message': str(e)
        })
