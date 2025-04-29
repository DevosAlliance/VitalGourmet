import json
from gluon import current
from datetime import datetime, timedelta, date
import logging
from decimal import Decimal
import datetime
from io import StringIO
from gluon.contrib.pymysql.err import IntegrityError

@auth.requires_login()
def api_top_a_la_carte():
    """
    API para obter os pratos à la carte mais pedidos no mês atual.
    
    Retorna um JSON contendo uma lista dos 3 pratos mais solicitados.
    """

    try:
        # Obtém a data atual
        hoje = request.now.date()
        mes_corrente = hoje.month
        ano_corrente = hoje.year

        # Consulta no banco para obter os pratos mais pedidos do tipo "À la carte"
        pratos_a_la_carte = db(
            (db.solicitacao_refeicao.prato_id == db.cardapio.id) & 
            ((db.cardapio.tipo == 'A la carte') | (db.cardapio.tipo == 'Livre')) &
            (db.solicitacao_refeicao.data_solicitacao.month() == mes_corrente) & 
            (db.solicitacao_refeicao.data_solicitacao.year() == ano_corrente)
        ).select(
            db.cardapio.nome, 
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_pedidos"),
            groupby=db.cardapio.nome,
            orderby=~db.solicitacao_refeicao.quantidade_solicitada.sum(),
            limitby=(0, 3)  # Pegamos apenas os 3 mais pedidos
        )

        # Estrutura os dados de resposta
        resultado = []
        for prato in pratos_a_la_carte:
            resultado.append({
                "nome": prato[db.cardapio.nome],
                "quantidade": prato["total_pedidos"]
            })

        # Retorna a resposta JSON
        return response.json({"status": "success", "top_a_la_carte": resultado})

    except Exception as e:
        return response.json({"status": "error", "message": str(e)})


@auth.requires_login()
def api_pedidos_mensais():
    """
    API para obter a quantidade de pedidos por tipo de refeição no mês atual.
    
    Retorna um JSON contendo os tipos de refeição e suas respectivas quantidades.
    """

    try:
        # Obtém a data atual
        hoje = request.now.date()
        mes_corrente = hoje.month
        ano_corrente = hoje.year

        # Define os tipos de pedidos que queremos exibir no gráfico
        tipos_refeicao = ["Almoço", "Jantar", "Café da Manhã", "Ceia", "Lanche", "A la carte", "Livre", "Bebidas"]

        # Armazena os resultados
        resultado = []

        # Faz uma consulta para cada tipo de refeição
        for tipo in tipos_refeicao:
            total_pedidos = db(
                (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
                (db.cardapio.tipo == tipo) &
                (db.solicitacao_refeicao.data_solicitacao.month() == mes_corrente) &
                (db.solicitacao_refeicao.data_solicitacao.year() == ano_corrente)
            ).select(
                db.solicitacao_refeicao.quantidade_solicitada.sum()
            ).first()[db.solicitacao_refeicao.quantidade_solicitada.sum()] or 0  # Caso não tenha pedidos, retorna 0.

            # Adiciona ao resultado
            resultado.append({"tipo": tipo, "quantidade": total_pedidos})

        # Retorna a resposta JSON
        return response.json({"status": "success", "pedidos_mensais": resultado})

    except Exception as e:
        return response.json({"status": "error", "message": str(e)})


@auth.requires_login()
def api_top_pratos():
    """
    Retorna os três pratos mais pedidos no mês atual, excluindo Bebidas, A la carte e Livre.
    """
    try:
        # Obtém a data atual
        hoje = request.now.date()
        mes_corrente = hoje.month
        ano_corrente = hoje.year

        pratos_mais_pedidos = db(
            (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
            ~(db.cardapio.tipo.belongs(['Bebidas', 'A la carte', 'Livre'])) &
            (db.solicitacao_refeicao.data_solicitacao.month() == mes_corrente) &
            (db.solicitacao_refeicao.data_solicitacao.year() == ano_corrente)
        ).select(
            db.cardapio.nome,
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_pedidos"),
            groupby=db.cardapio.nome,
            orderby=~db.solicitacao_refeicao.quantidade_solicitada.sum(),
            limitby=(0, 3)
        )

        resultado = [{"nome": prato[db.cardapio.nome], "quantidade": prato["total_pedidos"]} for prato in pratos_mais_pedidos]

        return response.json({"status": "success", "top_pratos": resultado})

    except Exception as e:
        return response.json({"status": "error", "message": str(e)})

@auth.requires_login()
def api_distribuicao_pedidos_semana():
    try:
        hoje = datetime.date.today()  
        inicio_periodo = hoje - datetime.timedelta(days=30)  

        dias_semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        resultado = {turno: {dia: 0 for dia in dias_semana} for turno in ["Manhã", "Tarde", "Noite"]}

        turnos = {
            "Manhã": (datetime.time(6, 0), datetime.time(12, 0)),
            "Tarde": (datetime.time(12, 0), datetime.time(18, 0)),
            "Noite": (datetime.time(18, 0), datetime.time(6, 0))
        }

        horarios = db().select(
            db.horario_refeicoes.id,
            db.horario_refeicoes.refeicao,
            db.horario_refeicoes.pedido_inicio,
            db.horario_refeicoes.pedido_fim
        )
        
        mapa_horarios = {}
        for h in horarios:
            mapa_horarios[h.refeicao] = {
                'inicio': h.pedido_inicio,
                'fim': h.pedido_fim
            }

        # Obtém os pedidos dentro do período com join para cardapio
        pedidos = db(
            (db.solicitacao_refeicao.data_solicitacao >= inicio_periodo) & 
            (db.solicitacao_refeicao.data_solicitacao <= hoje) &
            (db.solicitacao_refeicao.prato_id == db.cardapio.id)
        ).select(
            db.solicitacao_refeicao.data_solicitacao,
            db.solicitacao_refeicao.quantidade_solicitada,
            db.cardapio.tipo
        )

        for pedido in pedidos:
            data_pedido = pedido.solicitacao_refeicao.data_solicitacao
            quantidade = pedido.solicitacao_refeicao.quantidade_solicitada or 0
            tipo_refeicao = pedido.cardapio.tipo
            
            # Unificar "A la carte" e "Livre" em uma categoria
            if tipo_refeicao in ["A la carte", "Livre"]:
                tipo_refeicao = "A la carte"

            dia_semana = dias_semana[data_pedido.weekday()]
            
            # Determina o turno com base no tipo de refeição
            if (tipo_refeicao in mapa_horarios) or (tipo_refeicao == "A la carte/Livre" and ("A la carte" in mapa_horarios or "Livre" in mapa_horarios)):
                # Para o tipo unificado, verificar se algum dos tipos originais está no mapeamento
                if tipo_refeicao == "A la carte":
                    if "A la carte" in mapa_horarios:
                        horario_inicio = mapa_horarios["A la carte"]['inicio']
                        horario_fim = mapa_horarios["A la carte"]['fim']
                    elif "Livre" in mapa_horarios:
                        horario_inicio = mapa_horarios["Livre"]['inicio']
                        horario_fim = mapa_horarios["Livre"]['fim']
                    else:
                        # Caso nenhum dos dois esteja no mapeamento, usar valor padrão
                        horario_inicio = datetime.time(0, 0)
                        horario_fim = datetime.time(23, 59)
                else:
                    horario_inicio = mapa_horarios[tipo_refeicao]['inicio']
                    horario_fim = mapa_horarios[tipo_refeicao]['fim']
                
                # tipos que podem ocorrer em qualquer horário (A la carte/Livre, Bebidas)
                if tipo_refeicao in ["A la carte", "Bebidas"]:
                    for turno in ["Manhã", "Tarde", "Noite"]:
                        resultado[turno][dia_semana] += quantidade / 3
                else:
                    turno_identificado = None
                    
                    # turno da noite
                    if (horario_inicio >= turnos["Noite"][0]) or (horario_fim <= turnos["Noite"][1]):
                        turno_identificado = "Noite"
                    # turno da manhã
                    elif (turnos["Manhã"][0] <= horario_inicio < turnos["Manhã"][1]) or \
                         (turnos["Manhã"][0] < horario_fim <= turnos["Manhã"][1]):
                        turno_identificado = "Manhã"
                    # turno da tarde
                    elif (turnos["Tarde"][0] <= horario_inicio < turnos["Tarde"][1]) or \
                         (turnos["Tarde"][0] < horario_fim <= turnos["Tarde"][1]):
                        turno_identificado = "Tarde"
                    # Se o horário pegar mais de um turno, usar o turno de início
                    else:
                        # Determinar em qual turno começa
                        for turno, (hora_inicio, hora_fim) in turnos.items():
                            if turno == "Noite":
                                if horario_inicio >= hora_inicio or horario_inicio < hora_fim:
                                    turno_identificado = turno
                                    break
                            elif hora_inicio <= horario_inicio < hora_fim:
                                turno_identificado = turno
                                break
                        
                        # usar o turno da tarde como padrão, caso não identificado
                        if not turno_identificado:
                            turno_identificado = "Tarde"
                    
                    resultado[turno_identificado][dia_semana] += quantidade

        distribuicao_pedidos = []
        for turno, dados in resultado.items():
            for dia, quantidade in dados.items():
                quantidade_final = round(quantidade)
                if quantidade_final > 0: 
                    distribuicao_pedidos.append({
                        "dia_semana": dia, 
                        "turno": turno, 
                        "quantidade": quantidade_final
                    })

        return response.json({
            "status": "success", 
            "distribuicao_pedidos": distribuicao_pedidos
        })

    except Exception as e:
        import traceback
        return response.json({
            "status": "error", 
            "message": str(e),
            "traceback": traceback.format_exc()
        })
        
@auth.requires_login()
def api_top_bebidas():
    """
    Retorna as três bebidas mais pedidas no mês atual.
    Se não houver pedidos, retorna 0.
    """
    try:

        hoje = request.now.date()
        mes_corrente = hoje.month
        ano_corrente = hoje.year

        bebidas_mais_pedidas = db(
            (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
            (db.cardapio.tipo == "Bebidas") &  # Filtra apenas bebidas
            (db.solicitacao_refeicao.data_solicitacao.month() == mes_corrente) &
            (db.solicitacao_refeicao.data_solicitacao.year() == ano_corrente)
        ).select(
            db.cardapio.nome,
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_pedidos"),
            groupby=db.cardapio.nome,
            orderby=~db.solicitacao_refeicao.quantidade_solicitada.sum(),
            limitby=(0, 3)
        )

        # Formata o resultado
        resultado = []
        for bebida in bebidas_mais_pedidas:
            resultado.append({
                "nome": bebida.cardapio.nome,
                "quantidade": bebida["total_pedidos"]
            })


        if not resultado:
            return response.json({"status": "success", "top_bebidas": 0})


        return response.json({"status": "success", "top_bebidas": resultado})

    except Exception as e:
        print(f"Erro na API: {str(e)}")
        return response.json({"status": "error", "message": str(e)})




















































# dashboard
@auth.requires_login()
def index():
    import datetime
    hoje = datetime.datetime.now()
    mes_atual = hoje.month
    ano_atual = hoje.year

    # Quantidade de pratos cadastrados
    total_pratos = db(db.cardapio.id > 0).count()

    # Saldo total de pagamentos recebidos no mês atual
    saldo_mes = db((db.pagamentos.data_pagamento.month() == mes_atual) &
                   (db.pagamentos.data_pagamento.year() == ano_atual)).select(
        db.pagamentos.valor_pago.sum()
    ).first()[db.pagamentos.valor_pago.sum()] or 0

    # Quantidade total de pratos solicitados no mês atual
    total_vendas_mes = db((db.solicitacao_refeicao.data_solicitacao.month() == mes_atual) &
                          (db.solicitacao_refeicao.data_solicitacao.year() == ano_atual)).select(
        db.solicitacao_refeicao.quantidade_solicitada.sum()
    ).first()[db.solicitacao_refeicao.quantidade_solicitada.sum()] or 0

    # Número de colaboradores cadastrados
    total_colaboradores = db(db.auth_user.user_type == db(db.user_type.name == 'Colaborador').select(db.user_type.id).first().id).count()

    # Quantidade de pacientes cadastrados (somando Paciente e Paciente Convenio)
    total_pacientesN = db(db.auth_user.user_type == db(db.user_type.name == 'Paciente').select(db.user_type.id).first().id).count()
    total_pacientesC = db(db.auth_user.user_type == db(db.user_type.name == 'Paciente Convenio').select(db.user_type.id).first().id).count()
    total_pacientes = total_pacientesN + total_pacientesC

    # Quantidade de acompanhantes cadastrados
    total_acompanhantes = db(db.auth_user.user_type == db(db.user_type.name == 'Acompanhante').select(db.user_type.id).first().id).count()

    # Lucro total do ano (pagamentos)
    lucro_total_ano = db(db.pagamentos.data_pagamento.year() == ano_atual).select(
        db.pagamentos.valor_pago.sum()
    ).first()[db.pagamentos.valor_pago.sum()] or 0

    return dict(
        total_pratos=total_pratos,
        saldo_mes=saldo_mes,
        total_vendas_mes=total_vendas_mes,
        total_colaboradores=total_colaboradores,
        total_pacientes=total_pacientes,
        total_acompanhantes=total_acompanhantes,
        lucro_total_ano=lucro_total_ano,
    )


@auth.requires_login()
def api_dashboard_dados():
    try:
        # Consulta para contar pratos solicitados, agrupando por mês e ano
        pratos_por_mes = db(
            db.solicitacao_refeicao.id > 0
        ).select(
            db.solicitacao_refeicao.prato_id.count(),
            db.solicitacao_refeicao.data_solicitacao.year(),
            db.solicitacao_refeicao.data_solicitacao.month(),
            groupby=[db.solicitacao_refeicao.data_solicitacao.year(), db.solicitacao_refeicao.data_solicitacao.month()],
            distinct=True
        )

        # Consulta para contar usuários únicos que solicitaram, agrupando por mês e ano
        usuarios_por_mes = db(
            db.solicitacao_refeicao.id > 0
        ).select(
            db.solicitacao_refeicao.solicitante_id.count(distinct=True),
            db.solicitacao_refeicao.data_solicitacao.year(),
            db.solicitacao_refeicao.data_solicitacao.month(),
            groupby=[db.solicitacao_refeicao.data_solicitacao.year(), db.solicitacao_refeicao.data_solicitacao.month()],
            distinct=True
        )

        # Preparar dados para o JSON de resposta
        dados_pratos = []
        dados_usuarios = []

        for row in pratos_por_mes:
            dados_pratos.append({
                'ano': row[db.solicitacao_refeicao.data_solicitacao.year()],
                'mes': row[db.solicitacao_refeicao.data_solicitacao.month()],
                'pratos_solicitados': row[db.solicitacao_refeicao.prato_id.count()]
            })

        for row in usuarios_por_mes:
            dados_usuarios.append({
                'ano': row[db.solicitacao_refeicao.data_solicitacao.year()],
                'mes': row[db.solicitacao_refeicao.data_solicitacao.month()],
                'usuarios_solicitantes': row[db.solicitacao_refeicao.solicitante_id.count(distinct=True)]
            })

        return response.json({
            'status': 'success',
            'pratos_por_mes': dados_pratos,
            'usuarios_por_mes': dados_usuarios
        })
    except Exception as e:
        return response.json({
            'status': 'error',
            'message': str(e)
        })

@auth.requires_login()
def api_lucro_mensal():
    ano_atual = datetime.datetime.now().year
    lucro_por_mes = []

    # Calcula o lucro por mês
    for mes in range(1, 13):
        # Seleciona as solicitações do mês atual
        lucro_mes = db((db.solicitacao_refeicao.data_solicitacao.month() == mes) &
                       (db.solicitacao_refeicao.data_solicitacao.year() == ano_atual)).select(
            db.solicitacao_refeicao.preco.sum()
        ).first()[db.solicitacao_refeicao.preco.sum()] or 0

        lucro_por_mes.append({
            "ano": ano_atual,
            "mes": mes,
            "lucro": float(lucro_mes)  # Converte para float para evitar problemas de serialização
        })

    # Retorna o lucro mês a mês em formato JSON
    return response.json({"status": "success", "lucro_por_mes": lucro_por_mes})



# APIS dash
def api_pedidos_por_tipo():
    try:
        hoje_inicio = request.now.replace(hour=0, minute=0, second=0, microsecond=0)
        hoje_fim = hoje_inicio + timedelta(days=1)

        TIPOS_COLABORADORES = ['Administrador', 'Colaborador', 'Gestor', 'Instrumentador', 'Medico']
        TIPOS_PACIENTES = ['Paciente', 'Paciente Convenio', 'Acompanhante', 'Hemodialise']

        pratos_colaboradores = db(
            (db.solicitacao_refeicao.solicitante_id == db.auth_user.id) &
            (db.auth_user.user_type.belongs(
                db(db.user_type.name.belongs(TIPOS_COLABORADORES)).select(db.user_type.id)
            )) &
            (db.solicitacao_refeicao.data_solicitacao >= hoje_inicio) &
            (db.solicitacao_refeicao.data_solicitacao < hoje_fim)
        ).select(
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_pratos")
        ).first().total_pratos or 0

        pratos_pacientes = db(
            (db.solicitacao_refeicao.solicitante_id == db.auth_user.id) &
            (db.auth_user.user_type.belongs(
                db(db.user_type.name.belongs(TIPOS_PACIENTES)).select(db.user_type.id)
            )) &
            (db.solicitacao_refeicao.data_solicitacao >= hoje_inicio) &
            (db.solicitacao_refeicao.data_solicitacao < hoje_fim)
        ).select(
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_pratos")
        ).first().total_pratos or 0

        return response.json({
            "pratos_colaboradores": pratos_colaboradores,
            "pratos_pacientes": pratos_pacientes
        })
    except Exception as e:
        return response.json({"status": "erro", "mensagem": str(e)})

def api_pedidos_por_tipo_prato():
    try:
        hoje = request.now.date()
        mes_corrente = hoje.month
        ano_corrente = hoje.year

        # Soma das quantidades solicitadas para pratos (não "A la carte" ou "Livre")
        total_pratos = db(
            (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
            (~db.cardapio.tipo.belongs(['A la carte', 'Livre', 'Bebidas'])) &
            (db.solicitacao_refeicao.data_solicitacao.month() == mes_corrente) &
            (db.solicitacao_refeicao.data_solicitacao.year() == ano_corrente)
        ).select(
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_quantidade")
        ).first().total_quantidade or 0  # Retorna 0 se não houver registros.

        # Soma das quantidades solicitadas para pratos "A la carte" ou "Livre"
        total_a_la_carte = db(
            (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
            (db.cardapio.tipo.belongs(['A la carte', 'Livre', 'Bebidas'])) &
            (db.solicitacao_refeicao.data_solicitacao.month() == mes_corrente) &
            (db.solicitacao_refeicao.data_solicitacao.year() == ano_corrente)
        ).select(
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_quantidade")
        ).first().total_quantidade or 0  # Retorna 0 se não houver registros.


        # Soma das quantidades solicitadas para pratos Comuns
        total_comum = db(
            (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
            (db.cardapio.tipo.belongs(['Almoço', 'Café da Manhã', 'Ceia', 'Lanche', 'Jantar'])) &
            (db.solicitacao_refeicao.data_solicitacao.month() == mes_corrente) &
            (db.solicitacao_refeicao.data_solicitacao.year() == ano_corrente)
        ).select(
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_quantidade")
        ).first().total_quantidade or 0  # Retorna 0 se não houver registros.

        return response.json({
            "total_pratos": total_pratos,
            "total_a_la_carte": total_a_la_carte,
            "Total_pratos_comuns": total_comum
        })
    except Exception as e:
        return response.json({"status": "erro", "mensagem": str(e)})


def api_receita_a_la_carte():
    try:
        hoje = request.now.date()
        mes_corrente = hoje.month
        ano_corrente = hoje.year

        receita_hoje = db(
            (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
            (db.cardapio.tipo.belongs(['A la carte', 'Livre', 'Bebidas'])) &
            (db.solicitacao_refeicao.data_solicitacao == hoje)
        ).select(db.solicitacao_refeicao.preco.sum()).first()[db.solicitacao_refeicao.preco.sum()]

        receita_hoje_comum = db(
            (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
            (db.cardapio.tipo.belongs(['Almoço', 'Café da Manhã', 'Ceia', 'Lanche', 'Jantar'])) &
            (db.solicitacao_refeicao.data_solicitacao == hoje)
        ).select(db.solicitacao_refeicao.preco.sum()).first()[db.solicitacao_refeicao.preco.sum()]


        receita_mes = db(
            (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
            (db.cardapio.tipo.belongs(['A la carte', 'Livre', 'Bebidas'])) &
            (db.solicitacao_refeicao.data_solicitacao.month() == mes_corrente) &
            (db.solicitacao_refeicao.data_solicitacao.year() == ano_corrente)
        ).select(db.solicitacao_refeicao.preco.sum()).first()[db.solicitacao_refeicao.preco.sum()]

        receita_mes_comum = db(
            (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
            (db.cardapio.tipo.belongs(['Almoço', 'Café da Manhã', 'Ceia', 'Lanche', 'Jantar'])) &
            (db.solicitacao_refeicao.data_solicitacao.month() == mes_corrente) &
            (db.solicitacao_refeicao.data_solicitacao.year() == ano_corrente)
        ).select(db.solicitacao_refeicao.preco.sum()).first()[db.solicitacao_refeicao.preco.sum()]

        return response.json({
            "receita_hoje": receita_hoje or 0.0,
            "receita_mes": receita_mes or 0.0,
            "receita_hoje_comum": receita_hoje_comum or 0.00,
            "receita_mes_comum": receita_mes_comum or 0.00,
        })
    except Exception as e:
        return response.json({"status": "erro", "mensagem": str(e)})

def api_receita_semanal():
    try:
        from calendar import monthrange, weekday, SUNDAY, SATURDAY

        hoje = request.now.date()
        mes_corrente = hoje.month
        ano_corrente = hoje.year

        # Função para calcular o intervalo das semanas no mês
        def calcular_semanas(mes, ano):
            semanas = []
            _, dias_no_mes = monthrange(ano, mes)
            dia_inicio_mes = date(ano, mes, 1)

            semana_atual = 1
            inicio_semana = dia_inicio_mes

            for dia in range(1, dias_no_mes + 1):
                data_atual = date(ano, mes, dia)
                if weekday(ano, mes, dia) == SATURDAY or dia == dias_no_mes:
                    # Fecha uma semana
                    semanas.append({
                        "semana": semana_atual,
                        "inicio": inicio_semana,
                        "fim": data_atual
                    })
                    semana_atual += 1
                    if dia != dias_no_mes:
                        inicio_semana = data_atual + timedelta(days=1)
            return semanas

        semanas = calcular_semanas(mes_corrente, ano_corrente)
        receita_por_semana = []

        for semana in semanas:
            inicio_semana = semana["inicio"]
            fim_semana = semana["fim"]

            # Receita semanal para A La Carte e Livre
            receita_a_la_carte = db(
                (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
                (db.cardapio.tipo.belongs(['A la carte', 'Livre'])) &
                (db.solicitacao_refeicao.data_solicitacao >= inicio_semana) &
                (db.solicitacao_refeicao.data_solicitacao <= fim_semana)
            ).select(db.solicitacao_refeicao.preco.sum()).first()[db.solicitacao_refeicao.preco.sum()] or 0.0

            # Receita semanal para pratos convencionais
            receita_convencional = db(
                (db.solicitacao_refeicao.prato_id == db.cardapio.id) &
                (~db.cardapio.tipo.belongs(['A la carte', 'Livre'])) &
                (db.solicitacao_refeicao.data_solicitacao >= inicio_semana) &
                (db.solicitacao_refeicao.data_solicitacao <= fim_semana)
            ).select(db.solicitacao_refeicao.preco.sum()).first()[db.solicitacao_refeicao.preco.sum()] or 0.0

            receita_por_semana.append({
                "semana": semana["semana"],
                "receita_a_la_carte": receita_a_la_carte,
                "receita_convencional": receita_convencional
            })

        return response.json({
            "receita_por_semana": receita_por_semana
        })
    except Exception as e:
        return response.json({"status": "erro", "mensagem": str(e)})


def api_pedidos_por_setor_mes_corrente():
    try:
        hoje = request.now
        primeiro_dia_mes = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ultimo_dia_mes = (primeiro_dia_mes + timedelta(days=31)).replace(day=1) - timedelta(seconds=1)

        TIPOS_COLABORADORES = ['Administrador', 'Colaborador', 'Gestor', 'Instrumentador', 'Medico']
        TIPOS_PACIENTES = ['Paciente', 'Paciente Convenio', 'Acompanhante', 'Hemodialise']

        # Total de pedidos de colaboradores
        pedidos_colaboradores = db(
            (db.solicitacao_refeicao.solicitante_id == db.auth_user.id) &
            (
                (db.auth_user.user_type.belongs(
                    db(db.user_type.name.belongs(TIPOS_COLABORADORES)).select(db.user_type.id)
                )) |
                (
                    (db.auth_user.user_type == db(db.user_type.name == 'Hemodialise').select(db.user_type.id).first().id) &
                    (db.auth_user.setor_id == db(db.setor.name == 'Colaborador Hemodialise').select(db.setor.id).first().id)
                )
            ) &
            (db.solicitacao_refeicao.data_solicitacao >= primeiro_dia_mes) &
            (db.solicitacao_refeicao.data_solicitacao <= ultimo_dia_mes)
        ).select(
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_colaboradores")
        ).first().total_colaboradores or 0

        # Total de pedidos de pacientes
        pedidos_pacientes = db(
            (db.solicitacao_refeicao.solicitante_id == db.auth_user.id) &
            (
                (db.auth_user.user_type.belongs(
                    db(db.user_type.name.belongs(TIPOS_PACIENTES)).select(db.user_type.id)
                )) &
                ~(
                    (db.auth_user.user_type == db(db.user_type.name == 'Hemodialise').select(db.user_type.id).first().id) &
                    (db.auth_user.setor_id == db(db.setor.name == 'Colaborador Hemodialise').select(db.setor.id).first().id)
                )
            ) &
            (db.solicitacao_refeicao.data_solicitacao >= primeiro_dia_mes) &
            (db.solicitacao_refeicao.data_solicitacao <= ultimo_dia_mes)
        ).select(
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_pacientes")
        ).first().total_pacientes or 0

        # Total geral de pedidos
        total_pedidos = pedidos_colaboradores + pedidos_pacientes

        # Pedidos por setor
        setores = db(db.setor.id > 0).select()
        pedidos_por_setor = []
        for setor in setores:
            quantidade_pratos = db(
                (db.solicitacao_refeicao.solicitante_id == db.auth_user.id) &
                (db.auth_user.setor_id == setor.id) &
                (db.solicitacao_refeicao.data_solicitacao >= primeiro_dia_mes) &
                (db.solicitacao_refeicao.data_solicitacao <= ultimo_dia_mes)
            ).select(
                db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_quantidade")
            ).first().total_quantidade or 0

            pedidos_por_setor.append({
                "setor": setor.name,
                "setor_id": setor.id,
                "quantidade_pedidos": quantidade_pratos
            })

        # Retorno JSON com totais e dados por setor
        return response.json({
            "total_pedidos": total_pedidos,
            "total_pedidos_colaboradores": pedidos_colaboradores,
            "total_pedidos_pacientes": pedidos_pacientes,
            "pedidos_por_setor": pedidos_por_setor
        })
    except Exception as e:
        return response.json({"status": "erro", "mensagem": str(e)})

def api_pedidos_por_setor():
    try:
        hoje_inicio = request.now.replace(hour=0, minute=0, second=0, microsecond=0)
        hoje_fim = hoje_inicio + timedelta(days=1)

        # Definição dos tipos de usuários considerados pacientes
        tipos_pacientes = ['Paciente', 'Paciente Convenio', 'Acompanhante']

        # Obter as solicitações agrupadas por setor
        solicitacoes_por_setor = db(
            (db.solicitacao_refeicao.solicitante_id == db.auth_user.id) &
            (db.solicitacao_refeicao.data_solicitacao >= hoje_inicio) &
            (db.solicitacao_refeicao.data_solicitacao < hoje_fim) &
            (db.auth_user.setor_id == db.setor.id)
        ).select(
            db.setor.name,
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_pratos"),
            db.auth_user.user_type,
            db.auth_user.setor_id,
            groupby=[db.setor.name, db.auth_user.user_type, db.auth_user.setor_id]
        )

        # Variáveis de soma
        pratos_colaboradores = 0
        pratos_pacientes = 0

        # Organizar dados e calcular pratos
        dados_setores = []
        for solicitacao in solicitacoes_por_setor:
            setor = solicitacao.setor.name
            total_pratos = solicitacao.total_pratos or 0
            user_type_row = db.user_type(solicitacao.auth_user.user_type)  # Obter o tipo de usuário pelo ID
            user_type = user_type_row.name if user_type_row else None
            setor_usuario_row = db.setor(solicitacao.auth_user.setor_id)  # Obter o setor do usuário pelo ID
            setor_usuario = setor_usuario_row.name if setor_usuario_row else None

            # Verificar se o usuário é paciente ou colaborador
            if user_type in tipos_pacientes or (user_type == 'Hemodialise' and setor_usuario != 'Colaborador Hemodialise'):
                pratos_pacientes += total_pratos
            else:
                pratos_colaboradores += total_pratos

            # Adicionar aos dados de retorno
            dados_setores.append({
                "setor": setor,
                "tipo_usuario": user_type,
                "total_pratos": total_pratos
            })

        # Resposta JSON
        return response.json({
            "status": "success",
            "pratos_colaboradores": pratos_colaboradores,
            "pratos_pacientes": pratos_pacientes,
            "dados": dados_setores
        })

    except Exception as e:
        import traceback
        return response.json({
            "status": "error",
            "mensagem": str(e),
            "trace": traceback.format_exc()
        })

def api_pedidos_por_setor_dia_corrente():
    try:
        hoje_inicio = request.now.replace(hour=0, minute=0, second=0, microsecond=0)
        hoje_fim = hoje_inicio + timedelta(days=1) - timedelta(seconds=1)

        TIPOS_COLABORADORES = ['Administrador', 'Colaborador', 'Gestor', 'Instrumentador', 'Medico']
        TIPOS_PACIENTES = ['Paciente', 'Paciente Convenio', 'Acompanhante', 'Hemodialise']

        # Total de pedidos de colaboradores
        pedidos_colaboradores = db(
            (db.solicitacao_refeicao.solicitante_id == db.auth_user.id) &
            (
                (db.auth_user.user_type.belongs(
                    db(db.user_type.name.belongs(TIPOS_COLABORADORES)).select(db.user_type.id)
                )) |
                (
                    (db.auth_user.user_type == db(db.user_type.name == 'Hemodialise').select(db.user_type.id).first().id) &
                    (db.auth_user.setor_id == db(db.setor.name == 'Colaborador Hemodialise').select(db.setor.id).first().id)
                )
            ) &
            (db.solicitacao_refeicao.data_solicitacao >= hoje_inicio) &
            (db.solicitacao_refeicao.data_solicitacao <= hoje_fim)
        ).select(
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_colaboradores")
        ).first().total_colaboradores or 0

        # Total de pedidos de pacientes
        pedidos_pacientes = db(
            (db.solicitacao_refeicao.solicitante_id == db.auth_user.id) &
            (
                (db.auth_user.user_type.belongs(
                    db(db.user_type.name.belongs(TIPOS_PACIENTES)).select(db.user_type.id)
                )) &
                ~(
                    (db.auth_user.user_type == db(db.user_type.name == 'Hemodialise').select(db.user_type.id).first().id) &
                    (db.auth_user.setor_id == db(db.setor.name == 'Colaborador Hemodialise').select(db.setor.id).first().id)
                )
            ) &
            (db.solicitacao_refeicao.data_solicitacao >= hoje_inicio) &
            (db.solicitacao_refeicao.data_solicitacao <= hoje_fim)
        ).select(
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_pacientes")
        ).first().total_pacientes or 0

        # Total geral de pedidos
        total_pedidos = pedidos_colaboradores + pedidos_pacientes

        # Pedidos por setor
        setores = db(db.setor.id > 0).select()
        pedidos_por_setor = []
        for setor in setores:
            quantidade_pratos = db(
                (db.solicitacao_refeicao.solicitante_id == db.auth_user.id) &
                (db.auth_user.setor_id == setor.id) &
                (db.solicitacao_refeicao.data_solicitacao >= hoje_inicio) &
                (db.solicitacao_refeicao.data_solicitacao <= hoje_fim)
            ).select(
                db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias("total_quantidade")
            ).first().total_quantidade or 0

            pedidos_por_setor.append({
                "setor": setor.name,
                "setor_id": setor.id,
                "quantidade_pedidos": quantidade_pratos
            })

        # Retorno JSON com totais e dados por setor
        return response.json({
            "total_pedidos": total_pedidos,
            "total_pedidos_colaboradores": pedidos_colaboradores,
            "total_pedidos_pacientes": pedidos_pacientes,
            "pedidos_por_setor": pedidos_por_setor
        })
    except Exception as e:
        return response.json({"status": "erro", "mensagem": str(e)})