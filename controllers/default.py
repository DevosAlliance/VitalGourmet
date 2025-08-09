import json
from gluon import current
from datetime import datetime, timedelta, date
import logging
from decimal import Decimal
import datetime
from io import StringIO
from gluon.contrib.pymysql.err import IntegrityError  # Importar o erro específico


def get_current_time():
    """
    Função que retorna a hora atual no formato ISO 8601.
    """
    # Obtém a hora atual
    current_time = datetime.datetime.now().isoformat()

    # Retorna a hora em JSON
    return response.json({'current_time': current_time})


def finalizar_solicitacoes_expiradas():
    """
    Finaliza automaticamente solicitações de refeições pendentes que excedem o limite de 1 hora após o pedido_fim
    e são de dias anteriores, excluindo tipos de usuários e pratos especificados, mas mantendo os usuários
    Hemodialise do setor Colaborador Hemodialise.
    """
    

    # Buffer para armazenar logs
    logs = StringIO()

    # Hora e data atuais
    now = datetime.datetime.now()
    logs.write(f"<strong>[INFO]</strong> Horário atual: <strong>{now}</strong><br>")

    # Tipos de usuários e pratos a serem excluídos da finalização automática
    tipos_usuario_excluidos = {'Paciente', 'Paciente Convenio'}
    tipos_prato_excluidos = {'A la carte', 'Livre'}

    # Consulta todas as solicitações pendentes que não pertencem aos tipos de pratos excluídos
    solicitacoes = db(
        (~db.solicitacao_refeicao.status.belongs(['Finalizado', 'Pago'])) &
        (~db.cardapio.tipo.belongs(tipos_prato_excluidos))
    ).select(
        db.solicitacao_refeicao.id,
        db.solicitacao_refeicao.created_on,
        db.solicitacao_refeicao.solicitante_id,
        db.cardapio.tipo,
        db.cardapio.id,
        db.cardapio.nome,
        db.auth_user.user_type,
        db.auth_user.setor_id,
        db.setor.name,
        left=[
            db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
            db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
            db.setor.on(db.auth_user.setor_id == db.setor.id)
        ]
    )

    # Lista para armazenar IDs de solicitações finalizadas
    finalizados = []

    # Itera sobre as solicitações
    for solicitacao in solicitacoes:
        try:
            # Obter o tipo de usuário associado à solicitação
            user_type_row = db.user_type(solicitacao.auth_user.user_type)
            user_type = user_type_row.name if user_type_row else "Desconhecido"

            # Obter o setor associado à solicitação
            setor_name = solicitacao.setor.name if solicitacao.setor else "Desconhecido"

            # Ignorar usuários Hemodialise que não estão no setor Colaborador Hemodialise
            if user_type == 'Hemodialise' and setor_name != 'Colaborador Hemodialise':
                logs.write(f"<strong>[INFO]</strong> Solicitação <strong>{solicitacao.solicitacao_refeicao.id}</strong> ignorada: tipo de usuário Hemodialise fora do setor Colaborador Hemodialise.<br>")
                continue

            # Ignorar outros tipos de usuários excluídos
            if user_type in tipos_usuario_excluidos:
                logs.write(f"<strong>[INFO]</strong> Solicitação <strong>{solicitacao.solicitacao_refeicao.id}</strong> ignorada: tipo de usuário excluído ({user_type}).<br>")
                continue

            # Obter o horário de término (pedido_fim) associado ao tipo de refeição
            horario_refeicao = db(db.horario_refeicoes.refeicao == solicitacao.cardapio.tipo).select().first()
            if not horario_refeicao:
                logs.write(f"<strong>[WARN]</strong> Solicitação <strong>{solicitacao.solicitacao_refeicao.id}</strong> ignorada: horário não encontrado para o tipo de refeição ({solicitacao.cardapio.tipo}).<br>")
                continue

            pedido_fim = horario_refeicao.pedido_fim

            # Calcula o limite de 1 hora após o pedido_fim no dia da criação da solicitação
            limite = datetime.datetime.combine(solicitacao.solicitacao_refeicao.created_on.date(), pedido_fim) + datetime.timedelta(hours=1)

            # Log detalhado
            logs.write(f"<strong>[INFO]</strong> Solicitação <strong>{solicitacao.solicitacao_refeicao.id}</strong><br>")
            logs.write(f"&emsp;Tipo de usuário: <strong>{user_type}</strong><br>")
            logs.write(f"&emsp;Setor do usuário: <strong>{setor_name}</strong><br>")
            logs.write(f"&emsp;Tipo de prato: <strong>{solicitacao.cardapio.tipo}</strong><br>")
            logs.write(f"&emsp;Horário solicitado: <strong>{solicitacao.solicitacao_refeicao.created_on}</strong><br>")
            logs.write(f"&emsp;Horário limite: <strong>{limite}</strong><br>")
            logs.write(f"&emsp;Horário atual: <strong>{now}</strong><br>")

            # Calcula a diferença de tempo
            tempo_restante = limite - now
            if tempo_restante.total_seconds() < 0:
                logs.write(f"<span style='color:red;'>&emsp;**Excedeu o limite por {abs(tempo_restante)}!**</span><br>")
            else:
                logs.write(f"&emsp;Tempo restante: <strong>{tempo_restante}</strong><br>")

            # Finaliza a solicitação se o horário atual exceder o limite
            if now > limite:
                solicitacao.solicitacao_refeicao.update_record(status='Finalizado')
                finalizados.append(solicitacao.solicitacao_refeicao.id)
                db.commit()
                logs.write(f"<strong>[INFO]</strong> Solicitação <strong>{solicitacao.solicitacao_refeicao.id}</strong> finalizada com sucesso.<br>")
            else:
                logs.write(f"<strong>[INFO]</strong> Solicitação <strong>{solicitacao.solicitacao_refeicao.id}</strong> não finalizada: dentro do limite de tempo.<br>")

        except Exception as e:
            logs.write(f"<strong>[ERROR]</strong> Erro ao processar solicitação <strong>{solicitacao.solicitacao_refeicao.id}</strong>: {e}<br>")

    # Finalização do processamento
    logs.write("<strong>[INFO]</strong> Finalização de solicitações expiradas concluída.<br>")

    # Retornar logs juntamente com o resultado final em HTML
    resultado_final = f"Solicitações expiradas finalizadas: {finalizados}" if finalizados else "Nenhuma solicitação foi finalizada."
    logs_html = logs.getvalue().replace("\n", "<br>")  # Substituir quebras de linha por <br> para exibição em HTML

    return f"<html><body><pre>{logs_html}</pre><br><strong>{resultado_final}</strong></body></html>"




# ---- Action for login/register/etc (required for auth) -----
@cache.action(time_expire=86400, cache_model=cache.ram, public=True)
def user():
    """
    exposes:
    http://..../[app]/default/user/login
    http://..../[app]/default/user/logout
    http://..../[app]/default/user/register
    http://..../[app]/default/user/profile
    http://..../[app]/default/user/retrieve_password
    http://..../[app]/default/user/change_password
    http://..../[app]/default/user/bulk_register
    use @auth.requires_login()
        @auth.requires_membership('group name')
        @auth.requires_permission('read','table name',record_id)
    to decorate functions that need access control
    also notice there is http://..../[app]/appadmin/manage/auth to allow administrator to manage users
    """
    return dict(form=auth())


# autenticação
def user():
    """
    exposes:
    http://..../[app]/default/user/login
    http://..../[app]/default/user/logout
    http://..../[app]/default/user/register
    http://..../[app]/default/user/profile
    http://..../[app]/default/user/retrieve_password
    http://..../[app]/default/user/change_password
    http://..../[app]/default/user/bulk_register
    use @auth.requires_login()
        @auth.requires_membership('group name')
        @auth.requires_permission('read','table name',record_id)
    to decorate functions that need access control
    also notice there is http://..../[app]/appadmin/manage/auth to allow administrator to manage users
    """
    return dict(form=auth())

def login_colaborador():
    """
    Lógica de login manual para colaboradores
    """
    if request.env.request_method == 'POST':
        email = request.post_vars.email
        password = request.post_vars.password
        remember_me = request.post_vars.remember_me  # Verificar o checkbox "Lembrar-me"

        # Validação do e-mail
        if not IS_EMAIL()(email)[1] is None:
            session.flash = "Por favor, insira um e-mail válido."
            redirect(URL('default', 'user'))

        # Autenticação manual
        user = auth.login_bare(email, password)
        if user:
            # Define a duração da sessão para 30 dias se o checkbox estiver marcado
            if remember_me:
                session._timeout = 86400 * 30  # 30 dias em segundos

            session.flash = "Login realizado com sucesso!"
            redirect(URL('default', 'index'))
        else:
            session.flash = "E-mail ou senha incorretos."
            redirect(URL('default', 'user'))

    return dict()

def logout():
    """
    Função de logout que destrói a sessão e redireciona para a página de login.
    """
    auth.logout()
    session.flash = "Você saiu com sucesso!"
    redirect(URL('default', 'user', args=['login']))  # Redireciona para a página de login

# ---- action to server uploaded static content (required) ---
@cache.action()
def download():
    """
    allows downloading of uploaded files
    http://..../[app]/default/download/[filename]
    """
    return response.download(request, db)




def preparar_menu():
    if auth.user:
        auth.user.user_type_name = db.user_type[auth.user.user_type].name if auth.user.user_type else ""
        auth.user.setor_name = db.setor[auth.user.setor_id].name if auth.user.setor_id else ""
    else:
        auth.user.user_type_name = ""
        auth.user.setor_name = ""

@auth.requires_login()
def admin_pedidos():
    """
    Exibe as solicitações de refeições feitas por todos os usuários, com filtros por nome, tipo de usuário, setor, nome do prato e intervalo de datas.
    """
    filtro_nome = request.vars.nome or ""
    filtro_tipo_usuario = request.vars.tipo_usuario or ""
    filtro_setor = request.vars.setor or ""
    filtro_tipo_refeicao = request.vars.tipo_refeicao
    filtro_nome_prato = request.vars.nome_prato or ""
    data_inicio = request.vars.data_inicio or None
    data_fim = request.vars.data_fim or None
    pagina = int(request.vars.pagina or 1)
    registros_por_pagina = 10
    inicio = (pagina - 1) * registros_por_pagina

    # Query inicial
    query = (db.solicitacao_refeicao.id > 0)

    if filtro_nome:
        query &= db.auth_user.first_name.contains(filtro_nome)

    if filtro_nome_prato:
        query &= db.cardapio.nome.contains(filtro_nome_prato)

    if filtro_tipo_usuario:
        if filtro_tipo_usuario == "Colaboradores Generalizados":
            # Obter IDs dos tipos de usuário que fazem parte dos colaboradores
            user_types = db(db.user_type.name.belongs(['colaborador', 'medico', 'gestor', 'administrador', 'instrumentador'])).select(db.user_type.id)
            user_type_ids = [ut.id for ut in user_types]

            # Buscar o ID do setor "Colaborador Hemodiálise"
            setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
            setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None

            if setor_colaborador_hemodialise_id:
                # Buscar o ID do tipo de usuário "Hemodiálise"
                tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
                tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None

                # Incluir usuários que sejam:
                # 1️⃣ Qualquer um dos colaboradores generalizados OU
                # 2️⃣ Do setor "Colaborador Hemodiálise" E tenham tipo "Hemodiálise"
                query &= ((db.auth_user.user_type.belongs(user_type_ids)) |
                          ((db.auth_user.setor_id == setor_colaborador_hemodialise_id) & (db.auth_user.user_type == tipo_hemodialise_id)))

        elif filtro_tipo_usuario == "Pacientes Generalizados":
            # Obter IDs dos tipos de usuário que fazem parte dos pacientes
            user_types = db(db.user_type.name.belongs([
                'paciente', 'paciente convenio', 'acompanhante', 'hemodialise'
            ])).select(db.user_type.id)
            user_type_ids = [ut.id for ut in user_types]

            # Excluir "Hemodiálise" do setor "Colaborador Hemodiálise"
            setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
            setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None

            tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
            tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None

            query &= db.auth_user.user_type.belongs(user_type_ids)

            if setor_colaborador_hemodialise_id:
                query &= ~((db.auth_user.user_type == tipo_hemodialise_id) &
                           (db.auth_user.setor_id == setor_colaborador_hemodialise_id))

        else:
            user_type = db(db.user_type.name == filtro_tipo_usuario).select(db.user_type.id).first()
            if user_type:
                query &= (db.auth_user.user_type == user_type.id)

    if filtro_setor:
        query &= (db.auth_user.setor_id == int(filtro_setor))

    if data_inicio:
        query &= (db.solicitacao_refeicao.data_solicitacao >= data_inicio)
    if data_fim:
        query &= (db.solicitacao_refeicao.data_solicitacao <= data_fim)

    if filtro_tipo_refeicao == "especial":
        query &= (db.cardapio.tipo.belongs(["Livre", "A la carte", "Bebidas"]))

    if filtro_tipo_refeicao == "comum":
        query &= (db.cardapio.tipo.belongs(['Almoço', 'Café da Manhã', 'Ceia', 'Lanche', 'Jantar']))

    # Consulta com filtros aplicados
    pedidos_query = db(query).select(
        db.solicitacao_refeicao.ALL,
        db.cardapio.nome,
        db.cardapio.tipo,
        db.auth_user.first_name,
        db.auth_user.user_type,
        db.auth_user.setor_id,
        orderby=~db.solicitacao_refeicao.data_solicitacao,
        left=[
            db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
            db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id)
        ],
        limitby=(inicio, inicio + registros_por_pagina)
    )

    # Calcular totais gerais
    totais = db(query).select(
        db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
        db.solicitacao_refeicao.preco.sum().with_alias('preco_total'),
        db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_pratos'),
        left=[
            db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
            db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id)
        ]
    ).first()

    # NOVO: Calcular totais por tipo de refeição
    totais_por_tipo = db(query).select(
        db.cardapio.tipo,
        db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
        db.solicitacao_refeicao.preco.sum().with_alias('preco_total'),
        db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_pratos'),
        left=[
            db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
            db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id)
        ],
        groupby=db.cardapio.tipo,
        orderby=db.cardapio.tipo
    )

    # Transformar resultado em dicionário unificando "Livre" e "A la carte"
    resumo_por_tipo = {}
    for total in totais_por_tipo:
        tipo_original = total.cardapio.tipo or "Sem Tipo"
        
        # Unificar "Livre" e "A la carte"
        if tipo_original == "Livre":
            tipo = "A la carte"
        else:
            tipo = tipo_original
        
        # Se o tipo já existe, somar os valores
        if tipo in resumo_por_tipo:
            resumo_por_tipo[tipo]['pedidos'] += total.total_pedidos or 0
            resumo_por_tipo[tipo]['pratos'] += total.total_pratos or 0
            resumo_por_tipo[tipo]['receita'] += total.preco_total or 0
        else:
            resumo_por_tipo[tipo] = {
                'pedidos': total.total_pedidos or 0,
                'pratos': total.total_pratos or 0,
                'receita': total.preco_total or 0
            }

    total_pedidos = totais.total_pedidos or 0
    total_paginas = (total_pedidos // registros_por_pagina) + (1 if total_pedidos % registros_por_pagina > 0 else 0)

    # Substituindo o cache que usava TIPOS_USUARIO
    def get_all_user_types_plus_special():
        # Busca todos os tipos de usuário do banco de dados
        user_types = db(db.user_type).select(db.user_type.name, orderby=db.user_type.name)
        # Converte para lista de nomes
        tipos = [ut.name for ut in user_types]
        # Adiciona os tipos especiais
        tipos.extend(["Colaboradores Generalizados", "Pacientes Generalizados"])
        return tipos

    # Usando cache com a função atualizada
    tipos_usuario = cache.ram(
        'tipos_usuario_dynamic',
        get_all_user_types_plus_special,
        time_expire=300
    )
    
    setores = cache.ram('setores', lambda: db(db.setor.id > 0).select(), time_expire=300)

    return dict(
        preco_total=totais.preco_total or 0,
        total_pratos=totais.total_pratos or 0,
        pedidos=pedidos_query,
        tipos_usuario=tipos_usuario,
        setores=setores,
        tipos_refeicao=["especial"],
        pagina=pagina,
        total_pedidos=totais.total_pedidos or 0,
        total_paginas=total_paginas,
        registros_por_pagina=registros_por_pagina,
        filtro_tipo_refeicao=filtro_tipo_refeicao,
        filtro_nome_prato=filtro_nome_prato,
        # NOVO: Adicionando o resumo por tipo
        resumo_por_tipo=resumo_por_tipo
    )


@auth.requires_login()
def api_analytics_tipo_refeicao():
    """
    API para retornar analytics detalhados de um tipo de refeição específico
    """
    try:
        # Obter tipo de refeição para análise
        tipo_refeicao_analytics = request.vars.tipo_refeicao_analytics
        if not tipo_refeicao_analytics:
            raise ValueError("Tipo de refeição não especificado")

        # Aplicar os mesmos filtros da página principal
        filtro_nome = request.vars.nome or ""
        filtro_tipo_usuario = request.vars.tipo_usuario or ""
        filtro_setor = request.vars.setor or ""
        filtro_tipo_refeicao = request.vars.tipo_refeicao
        filtro_nome_prato = request.vars.nome_prato or ""
        data_inicio = request.vars.data_inicio or None
        data_fim = request.vars.data_fim or None

        # Query base - mesma lógica da função admin_pedidos
        query = (db.solicitacao_refeicao.id > 0)

        # Filtro específico para o tipo de refeição da análise
        if tipo_refeicao_analytics == "A la carte":
            # Para A la carte, incluir tanto "A la carte" quanto "Livre"
            query &= db.cardapio.tipo.belongs(["A la carte", "Livre"])
        else:
            query &= (db.cardapio.tipo == tipo_refeicao_analytics)

        # Aplicar filtros adicionais
        if filtro_nome:
            query &= db.auth_user.first_name.contains(filtro_nome)

        if filtro_nome_prato:
            query &= db.cardapio.nome.contains(filtro_nome_prato)

        if filtro_tipo_usuario:
            if filtro_tipo_usuario == "Colaboradores Generalizados":
                user_types = db(db.user_type.name.belongs(['colaborador', 'medico', 'gestor', 'administrador', 'instrumentador'])).select(db.user_type.id)
                user_type_ids = [ut.id for ut in user_types]

                setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
                setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None

                if setor_colaborador_hemodialise_id:
                    tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
                    tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None

                    query &= ((db.auth_user.user_type.belongs(user_type_ids)) |
                              ((db.auth_user.setor_id == setor_colaborador_hemodialise_id) & (db.auth_user.user_type == tipo_hemodialise_id)))

            elif filtro_tipo_usuario == "Pacientes Generalizados":
                user_types = db(db.user_type.name.belongs([
                    'paciente', 'paciente convenio', 'acompanhante', 'hemodialise'
                ])).select(db.user_type.id)
                user_type_ids = [ut.id for ut in user_types]

                setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
                setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None

                tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
                tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None

                query &= db.auth_user.user_type.belongs(user_type_ids)

                if setor_colaborador_hemodialise_id:
                    query &= ~((db.auth_user.user_type == tipo_hemodialise_id) &
                               (db.auth_user.setor_id == setor_colaborador_hemodialise_id))
            else:
                user_type = db(db.user_type.name == filtro_tipo_usuario).select(db.user_type.id).first()
                if user_type:
                    query &= (db.auth_user.user_type == user_type.id)

        if filtro_setor:
            query &= (db.auth_user.setor_id == int(filtro_setor))

        if data_inicio:
            query &= (db.solicitacao_refeicao.data_solicitacao >= data_inicio)
        if data_fim:
            query &= (db.solicitacao_refeicao.data_solicitacao <= data_fim)

        if filtro_tipo_refeicao == "especial":
            query &= (db.cardapio.tipo.belongs(["Livre", "A la carte", "Bebidas"]))
        elif filtro_tipo_refeicao == "comum":
            query &= (db.cardapio.tipo.belongs(['Almoço', 'Café da Manhã', 'Ceia', 'Lanche', 'Jantar']))

        # 1. ANALYTICS POR TIPO DE USUÁRIO
        analytics_por_tipo = db(query).select(
            db.user_type.name.with_alias('tipo_usuario'),
            db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_unidades'),
            db.solicitacao_refeicao.preco.sum().with_alias('total_receita'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.user_type.on(db.auth_user.user_type == db.user_type.id)
            ],
            groupby=db.user_type.name,
            orderby=~db.solicitacao_refeicao.preco.sum()
        )

        # 2. ANALYTICS POR SETOR
        analytics_por_setor = db(query).select(
            db.setor.name.with_alias('setor'),
            db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_unidades'),
            db.solicitacao_refeicao.preco.sum().with_alias('total_receita'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ],
            groupby=db.setor.name,
            orderby=~db.solicitacao_refeicao.preco.sum()
        )

        # 3. TOTAIS GERAIS
        totais_gerais = db(query).select(
            db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_unidades'),
            db.solicitacao_refeicao.preco.sum().with_alias('total_receita'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id)
            ]
        ).first()

        # Processar dados por tipo de usuário
        dados_por_tipo = []
        for item in analytics_por_tipo:
            if item.tipo_usuario:  # Só incluir se tiver tipo de usuário
                dados_por_tipo.append({
                    'tipo_usuario': item.tipo_usuario,
                    'total_pedidos': int(item.total_pedidos or 0),
                    'total_unidades': int(item.total_unidades or 0),
                    'total_receita': float(item.total_receita or 0)
                })

        # Processar dados por setor
        dados_por_setor = []
        for item in analytics_por_setor:
            dados_por_setor.append({
                'setor': item.setor or 'Sem setor definido',
                'total_pedidos': int(item.total_pedidos or 0),
                'total_unidades': int(item.total_unidades or 0),
                'total_receita': float(item.total_receita or 0)
            })

        # Calcular resumo geral
        total_pedidos = int(totais_gerais.total_pedidos or 0)
        total_unidades = int(totais_gerais.total_unidades or 0)
        total_receita = float(totais_gerais.total_receita or 0)
        media_por_pedido = total_receita / total_pedidos if total_pedidos > 0 else 0

        resumo_geral = {
            'total_pedidos': total_pedidos,
            'total_unidades': total_unidades,
            'total_receita': total_receita,
            'media_por_pedido': media_por_pedido
        }

        return response.json({
            'status': 'success',
            'tipo_refeicao': tipo_refeicao_analytics,
            'resumo_geral': resumo_geral,
            'por_tipo_usuario': dados_por_tipo,
            'por_setor': dados_por_setor,
            'timestamp': str(request.now)
        })

    except Exception as e:
        return response.json({
            'status': 'error',
            'message': str(e)
        })

@auth.requires_login()
def api_analytics_geral():
    """
    API para retornar analytics detalhados de TODOS os tipos de refeição
    """
    try:
        # Aplicar os mesmos filtros da página principal (sem filtro de tipo de refeição)
        filtro_nome = request.vars.nome or ""
        filtro_tipo_usuario = request.vars.tipo_usuario or ""
        filtro_setor = request.vars.setor or ""
        filtro_nome_prato = request.vars.nome_prato or ""
        data_inicio = request.vars.data_inicio or None
        data_fim = request.vars.data_fim or None

        # Query base - mesma lógica da função admin_pedidos mas SEM filtro de tipo
        query = (db.solicitacao_refeicao.id > 0)

        # Aplicar filtros (mesma lógica do admin_pedidos)
        if filtro_nome:
            query &= db.auth_user.first_name.contains(filtro_nome)

        if filtro_nome_prato:
            query &= db.cardapio.nome.contains(filtro_nome_prato)

        if filtro_tipo_usuario:
            if filtro_tipo_usuario == "Colaboradores Generalizados":
                # Obter IDs dos tipos de usuário que fazem parte dos colaboradores
                user_types = db(db.user_type.name.belongs(['colaborador', 'medico', 'gestor', 'administrador', 'instrumentador'])).select(db.user_type.id)
                user_type_ids = [ut.id for ut in user_types]

                # Buscar o ID do setor "Colaborador Hemodiálise"
                setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
                setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None

                if setor_colaborador_hemodialise_id:
                    # Buscar o ID do tipo de usuário "Hemodiálise"
                    tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
                    tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None

                    # Incluir usuários que sejam:
                    # 1️⃣ Qualquer um dos colaboradores generalizados OU
                    # 2️⃣ Do setor "Colaborador Hemodiálise" E tenham tipo "Hemodiálise"
                    query &= ((db.auth_user.user_type.belongs(user_type_ids)) |
                              ((db.auth_user.setor_id == setor_colaborador_hemodialise_id) & (db.auth_user.user_type == tipo_hemodialise_id)))

            elif filtro_tipo_usuario == "Pacientes Generalizados":
                # Obter IDs dos tipos de usuário que fazem parte dos pacientes
                user_types = db(db.user_type.name.belongs([
                    'paciente', 'paciente convenio', 'acompanhante', 'hemodialise'
                ])).select(db.user_type.id)
                user_type_ids = [ut.id for ut in user_types]

                # Excluir "Hemodiálise" do setor "Colaborador Hemodiálise"
                setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
                setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None

                tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
                tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None

                query &= db.auth_user.user_type.belongs(user_type_ids)

                if setor_colaborador_hemodialise_id:
                    query &= ~((db.auth_user.user_type == tipo_hemodialise_id) &
                               (db.auth_user.setor_id == setor_colaborador_hemodialise_id))

            else:
                user_type = db(db.user_type.name == filtro_tipo_usuario).select(db.user_type.id).first()
                if user_type:
                    query &= (db.auth_user.user_type == user_type.id)

        if filtro_setor:
            query &= (db.auth_user.setor_id == int(filtro_setor))

        if data_inicio:
            query &= (db.solicitacao_refeicao.data_solicitacao >= data_inicio)
        if data_fim:
            query &= (db.solicitacao_refeicao.data_solicitacao <= data_fim)

        # ANALYTICS POR TIPO DE USUÁRIO
        analytics_por_tipo = db(query).select(
            db.user_type.name.with_alias('tipo_usuario'),
            db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_unidades'),
            db.solicitacao_refeicao.preco.sum().with_alias('total_receita'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.user_type.on(db.auth_user.user_type == db.user_type.id)
            ],
            groupby=db.user_type.name,
            orderby=~db.solicitacao_refeicao.preco.sum()
        )

        # ANALYTICS POR SETOR
        analytics_por_setor = db(query).select(
            db.setor.name.with_alias('setor'),
            db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_unidades'),
            db.solicitacao_refeicao.preco.sum().with_alias('total_receita'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ],
            groupby=db.setor.name,
            orderby=~db.solicitacao_refeicao.preco.sum()
        )

        # ANALYTICS POR TIPO DE REFEIÇÃO (novo!)
        analytics_por_tipo_refeicao = db(query).select(
            db.cardapio.tipo.with_alias('tipo_refeicao'),
            db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_unidades'),
            db.solicitacao_refeicao.preco.sum().with_alias('total_receita'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id)
            ],
            groupby=db.cardapio.tipo,
            orderby=~db.solicitacao_refeicao.preco.sum()
        )

        # TOTAIS GERAIS
        totais_gerais = db(query).select(
            db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_unidades'),
            db.solicitacao_refeicao.preco.sum().with_alias('total_receita'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id)
            ]
        ).first()

        # Processar dados por tipo de usuário
        dados_por_tipo = []
        for item in analytics_por_tipo:
            if item.tipo_usuario:  # Só incluir se tiver tipo de usuário
                dados_por_tipo.append({
                    'tipo_usuario': item.tipo_usuario,
                    'total_pedidos': int(item.total_pedidos or 0),
                    'total_unidades': int(item.total_unidades or 0),
                    'total_receita': float(item.total_receita or 0)
                })

        # Processar dados por setor
        dados_por_setor = []
        for item in analytics_por_setor:
            dados_por_setor.append({
                'setor': item.setor or 'Sem setor definido',
                'total_pedidos': int(item.total_pedidos or 0),
                'total_unidades': int(item.total_unidades or 0),
                'total_receita': float(item.total_receita or 0)
            })
        
        # NOVO: Processar dados por tipo de refeição
        dados_por_tipo_refeicao = []
        resumo_unificado = {}
        
        for item in analytics_por_tipo_refeicao:
            if item.tipo_refeicao:
                tipo_original = item.tipo_refeicao
                
                # Unificar "Livre" e "A la carte" como na função admin_pedidos
                if tipo_original == "Livre":
                    tipo = "A la carte"
                else:
                    tipo = tipo_original
                
                # Se o tipo já existe, somar os valores
                if tipo in resumo_unificado:
                    resumo_unificado[tipo]['total_pedidos'] += int(item.total_pedidos or 0)
                    resumo_unificado[tipo]['total_unidades'] += int(item.total_unidades or 0)
                    resumo_unificado[tipo]['total_receita'] += float(item.total_receita or 0)
                else:
                    resumo_unificado[tipo] = {
                        'tipo_refeicao': tipo,
                        'total_pedidos': int(item.total_pedidos or 0),
                        'total_unidades': int(item.total_unidades or 0),
                        'total_receita': float(item.total_receita or 0)
                    }
        
        # Converter dicionário para lista ordenada por receita
        dados_por_tipo_refeicao = sorted(
            resumo_unificado.values(),
            key=lambda x: x['total_receita'],
            reverse=True
        )

        # Calcular resumo geral
        total_pedidos = int(totais_gerais.total_pedidos or 0)
        total_unidades = int(totais_gerais.total_unidades or 0)
        total_receita = float(totais_gerais.total_receita or 0)
        media_por_pedido = total_receita / total_pedidos if total_pedidos > 0 else 0

        resumo_geral = {
            'total_pedidos': total_pedidos,
            'total_unidades': total_unidades,
            'total_receita': total_receita,
            'media_por_pedido': media_por_pedido
        }

        return response.json({
            'status': 'success',
            'tipo_refeicao': 'TOTAL_GERAL',
            'resumo_geral': resumo_geral,
            'por_tipo_usuario': dados_por_tipo,
            'por_setor': dados_por_setor,
            'por_tipo_refeicao': dados_por_tipo_refeicao,
            'timestamp': str(request.now)
        })

    except Exception as e:
        import traceback
        print("Erro na api_analytics_geral:", str(e))
        print("Traceback:", traceback.format_exc())
        return response.json({
            'status': 'error', 
            'message': str(e),
            'debug': traceback.format_exc() if request.is_local else None
        })


@auth.requires_login()
def api_detalhes_usuarios_por_tipo():
    """
    API para retornar detalhes individuais dos usuários por tipo
    """
    try:
        # Obter tipo de usuário específico
        tipo_usuario_detalhes = request.vars.tipo_usuario_detalhes
        if not tipo_usuario_detalhes:
            raise ValueError("Tipo de usuário não especificado")

        # Aplicar os mesmos filtros da página principal
        filtro_nome = request.vars.nome or ""
        filtro_tipo_refeicao_analytics = request.vars.tipo_refeicao_analytics
        filtro_setor = request.vars.setor or ""
        filtro_tipo_refeicao = request.vars.tipo_refeicao
        filtro_nome_prato = request.vars.nome_prato or ""
        data_inicio = request.vars.data_inicio or None
        data_fim = request.vars.data_fim or None

        # Query base
        query = (db.solicitacao_refeicao.id > 0)

        # Filtro por tipo de refeição específico (se não for TOTAL_GERAL)
        if filtro_tipo_refeicao_analytics and filtro_tipo_refeicao_analytics != 'TOTAL_GERAL':
            if filtro_tipo_refeicao_analytics == "A la carte":
                query &= db.cardapio.tipo.belongs(["A la carte", "Livre"])
            else:
                query &= (db.cardapio.tipo == filtro_tipo_refeicao_analytics)

        # Filtro por tipo de usuário específico
        if tipo_usuario_detalhes == "Colaboradores Generalizados":
            user_types = db(db.user_type.name.belongs(['colaborador', 'medico', 'gestor', 'administrador', 'instrumentador'])).select(db.user_type.id)
            user_type_ids = [ut.id for ut in user_types]
            setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
            setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None
            if setor_colaborador_hemodialise_id:
                tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
                tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None
                query &= ((db.auth_user.user_type.belongs(user_type_ids)) |
                          ((db.auth_user.setor_id == setor_colaborador_hemodialise_id) & (db.auth_user.user_type == tipo_hemodialise_id)))
        elif tipo_usuario_detalhes == "Pacientes Generalizados":
            user_types = db(db.user_type.name.belongs(['paciente', 'paciente convenio', 'acompanhante', 'hemodialise'])).select(db.user_type.id)
            user_type_ids = [ut.id for ut in user_types]
            setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
            setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None
            tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
            tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None
            query &= db.auth_user.user_type.belongs(user_type_ids)
            if setor_colaborador_hemodialise_id:
                query &= ~((db.auth_user.user_type == tipo_hemodialise_id) &
                           (db.auth_user.setor_id == setor_colaborador_hemodialise_id))
        else:
            user_type = db(db.user_type.name == tipo_usuario_detalhes).select(db.user_type.id).first()
            if user_type:
                query &= (db.auth_user.user_type == user_type.id)

        # Aplicar outros filtros
        if filtro_nome:
            query &= db.auth_user.first_name.contains(filtro_nome)
        if filtro_nome_prato:
            query &= db.cardapio.nome.contains(filtro_nome_prato)
        if filtro_setor:
            query &= (db.auth_user.setor_id == int(filtro_setor))
        if data_inicio:
            query &= (db.solicitacao_refeicao.data_solicitacao >= data_inicio)
        if data_fim:
            query &= (db.solicitacao_refeicao.data_solicitacao <= data_fim)
        if filtro_tipo_refeicao == "especial":
            query &= (db.cardapio.tipo.belongs(["Livre", "A la carte", "Bebidas"]))
        elif filtro_tipo_refeicao == "comum":
            query &= (db.cardapio.tipo.belongs(['Almoço', 'Café da Manhã', 'Ceia', 'Lanche', 'Jantar']))

        # Buscar dados agrupados por usuário
        usuarios_detalhes = db(query).select(
            db.auth_user.first_name.with_alias('nome_usuario'),
            db.setor.name.with_alias('setor'),
            db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_unidades'),
            db.solicitacao_refeicao.preco.sum().with_alias('total_gasto'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ],
            groupby=[db.auth_user.first_name, db.setor.name],
            orderby=~db.solicitacao_refeicao.preco.sum()
        )

        # Processar dados
        dados_usuarios = []
        total_usuarios = 0
        receita_total = 0

        for usuario in usuarios_detalhes:
            total_gasto = float(usuario.total_gasto or 0)
            total_pedidos = int(usuario.total_pedidos or 0)
            media_pedido = total_gasto / total_pedidos if total_pedidos > 0 else 0
            
            dados_usuarios.append({
                'nome_usuario': usuario.nome_usuario,
                'setor': usuario.setor or 'Sem setor',
                'total_pedidos': total_pedidos,
                'total_unidades': int(usuario.total_unidades or 0),
                'total_gasto': total_gasto,
                'media_por_pedido': media_pedido
            })
            
            total_usuarios += 1
            receita_total += total_gasto

        return response.json({
            'status': 'success',
            'tipo_usuario': tipo_usuario_detalhes,
            'usuarios': dados_usuarios,
            'resumo': {
                'total_usuarios': total_usuarios,
                'receita_total': receita_total
            }
        })

    except Exception as e:
        import traceback
        return response.json({
            'status': 'error',
            'message': str(e),
            'debug': traceback.format_exc() if request.is_local else None
        })
    
@auth.requires_login()
def api_detalhes_usuarios_por_setor():
    """
    API para retornar detalhes individuais dos usuários por setor
    """
    try:
        # Obter setor específico
        setor_detalhes = request.vars.setor_detalhes
        if not setor_detalhes:
            raise ValueError("Setor não especificado")

        # Aplicar os mesmos filtros da página principal
        filtro_nome = request.vars.nome or ""
        filtro_tipo_refeicao_analytics = request.vars.tipo_refeicao_analytics
        filtro_tipo_usuario = request.vars.tipo_usuario or ""
        filtro_tipo_refeicao = request.vars.tipo_refeicao
        filtro_nome_prato = request.vars.nome_prato or ""
        data_inicio = request.vars.data_inicio or None
        data_fim = request.vars.data_fim or None

        # Query base
        query = (db.solicitacao_refeicao.id > 0)

        # Filtro por tipo de refeição específico (se não for TOTAL_GERAL)
        if filtro_tipo_refeicao_analytics and filtro_tipo_refeicao_analytics != 'TOTAL_GERAL':
            if filtro_tipo_refeicao_analytics == "A la carte":
                query &= db.cardapio.tipo.belongs(["A la carte", "Livre"])
            else:
                query &= (db.cardapio.tipo == filtro_tipo_refeicao_analytics)

        # Filtro por setor específico
        if setor_detalhes == "Sem setor definido":
            query &= (db.auth_user.setor_id == None)
        else:
            setor_obj = db(db.setor.name == setor_detalhes).select(db.setor.id).first()
            if setor_obj:
                query &= (db.auth_user.setor_id == setor_obj.id)
            else:
                raise ValueError("Setor não encontrado")

        # Aplicar outros filtros
        if filtro_nome:
            query &= db.auth_user.first_name.contains(filtro_nome)
        if filtro_nome_prato:
            query &= db.cardapio.nome.contains(filtro_nome_prato)
        
        # Filtro por tipo de usuário
        if filtro_tipo_usuario:
            if filtro_tipo_usuario == "Colaboradores Generalizados":
                user_types = db(db.user_type.name.belongs(['colaborador', 'medico', 'gestor', 'administrador', 'instrumentador'])).select(db.user_type.id)
                user_type_ids = [ut.id for ut in user_types]
                setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
                setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None
                if setor_colaborador_hemodialise_id:
                    tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
                    tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None
                    query &= ((db.auth_user.user_type.belongs(user_type_ids)) |
                              ((db.auth_user.setor_id == setor_colaborador_hemodialise_id) & (db.auth_user.user_type == tipo_hemodialise_id)))
            elif filtro_tipo_usuario == "Pacientes Generalizados":
                user_types = db(db.user_type.name.belongs(['paciente', 'paciente convenio', 'acompanhante', 'hemodialise'])).select(db.user_type.id)
                user_type_ids = [ut.id for ut in user_types]
                setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
                setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None
                tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
                tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None
                query &= db.auth_user.user_type.belongs(user_type_ids)
                if setor_colaborador_hemodialise_id:
                    query &= ~((db.auth_user.user_type == tipo_hemodialise_id) &
                               (db.auth_user.setor_id == setor_colaborador_hemodialise_id))
            else:
                user_type = db(db.user_type.name == filtro_tipo_usuario).select(db.user_type.id).first()
                if user_type:
                    query &= (db.auth_user.user_type == user_type.id)

        if data_inicio:
            query &= (db.solicitacao_refeicao.data_solicitacao >= data_inicio)
        if data_fim:
            query &= (db.solicitacao_refeicao.data_solicitacao <= data_fim)
        if filtro_tipo_refeicao == "especial":
            query &= (db.cardapio.tipo.belongs(["Livre", "A la carte", "Bebidas"]))
        elif filtro_tipo_refeicao == "comum":
            query &= (db.cardapio.tipo.belongs(['Almoço', 'Café da Manhã', 'Ceia', 'Lanche', 'Jantar']))

        # Buscar dados agrupados por usuário
        usuarios_detalhes = db(query).select(
            db.auth_user.first_name.with_alias('nome_usuario'),
            db.user_type.name.with_alias('tipo_usuario'),
            db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_unidades'),
            db.solicitacao_refeicao.preco.sum().with_alias('total_gasto'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.user_type.on(db.auth_user.user_type == db.user_type.id)
            ],
            groupby=[db.auth_user.first_name, db.user_type.name],
            orderby=~db.solicitacao_refeicao.preco.sum()
        )

        # Processar dados
        dados_usuarios = []
        total_usuarios = 0
        receita_total = 0

        for usuario in usuarios_detalhes:
            total_gasto = float(usuario.total_gasto or 0)
            total_pedidos = int(usuario.total_pedidos or 0)
            media_pedido = total_gasto / total_pedidos if total_pedidos > 0 else 0
            
            dados_usuarios.append({
                'nome_usuario': usuario.nome_usuario,
                'tipo_usuario': usuario.tipo_usuario or 'Sem tipo',
                'total_pedidos': total_pedidos,
                'total_unidades': int(usuario.total_unidades or 0),
                'total_gasto': total_gasto,
                'media_por_pedido': media_pedido
            })
            
            total_usuarios += 1
            receita_total += total_gasto

        return response.json({
            'status': 'success',
            'setor': setor_detalhes,
            'usuarios': dados_usuarios,
            'resumo': {
                'total_usuarios': total_usuarios,
                'receita_total': receita_total
            }
        })

    except Exception as e:
        import traceback
        return response.json({
            'status': 'error',
            'message': str(e),
            'debug': traceback.format_exc() if request.is_local else None
        })

# Função auxiliar para debug dos analytics (opcional)
@auth.requires_login()
def debug_analytics():
    """
    Função para debug dos dados de analytics
    """
    try:
        tipo_refeicao = request.args(0) or 'Almoço'
        
        # Query base
        query = (db.solicitacao_refeicao.id > 0) & (db.cardapio.tipo == tipo_refeicao)
        
        # Dados brutos
        dados_brutos = db(query).select(
            db.solicitacao_refeicao.ALL,
            db.cardapio.nome,
            db.cardapio.tipo,
            db.auth_user.first_name,
            db.user_type.name.with_alias('tipo_usuario'),
            db.setor.name.with_alias('setor'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.user_type.on(db.auth_user.user_type == db.user_type.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ]
        )
        
        # Analytics agregados
        por_tipo = db(query).select(
            db.user_type.name.with_alias('tipo_usuario'),
            db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_unidades'),
            db.solicitacao_refeicao.preco.sum().with_alias('total_receita'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.user_type.on(db.auth_user.user_type == db.user_type.id)
            ],
            groupby=db.user_type.name
        )
        
        return dict(
            tipo_refeicao=tipo_refeicao,
            total_registros=len(dados_brutos),
            dados_brutos=dados_brutos,
            por_tipo=por_tipo,
            estrutura_tabelas={
                'solicitacao_refeicao': db.solicitacao_refeicao.fields,
                'cardapio': db.cardapio.fields,
                'auth_user': db.auth_user.fields,
                'user_type': db.user_type.fields,
                'setor': db.setor.fields
            }
        )
        
    except Exception as e:
        return dict(erro=str(e))


# Função adicional para otimização (opcional)
@auth.requires_login()
def limpar_cache_analytics():
    """
    Função para limpar cache de analytics se necessário
    """
    try:
        # Limpar cache do web2py se estiver usando
        cache.ram.clear()
        
        return response.json({
            'status': 'success',
            'message': 'Cache de analytics limpo com sucesso'
        })
        
    except Exception as e:
        return response.json({
            'status': 'error',
            'message': str(e)
        })
    

def custom_login():
    if request.env.request_method == 'POST':
        cpf = request.post_vars.cpf.replace('.', '').replace('-', '')  # Remove formatação
        birth_date_str = request.post_vars.birth_date

        try:
            birth_date = datetime.datetime.strptime(birth_date_str, '%Y-%m-%d').date()
        except ValueError:
            response.flash = "Formato de data inválido. Use YYYY-MM-DD."
            return dict(form=FORM(INPUT(_name='cpf', _placeholder='CPF', _class='form-control'),
                                  INPUT(_name='birth_date', _placeholder='Data de Nascimento', _type='date', _class='form-control'),
                                  INPUT(_type='submit', _value='Entrar', _class='btn btn-primary')))

        tipos_restritos = db(db.user_type.name.belongs(['Administrador', 'Colaborador', 'Gestor'])).select(db.user_type.id)
        tipos_restritos_ids = [tipo.id for tipo in tipos_restritos]

        user = db((db.auth_user.cpf == cpf) &
                  (db.auth_user.birth_date == birth_date) &
                  (~db.auth_user.user_type.belongs(tipos_restritos_ids))).select().first()

        if user:
            auth.login_user(user)
            redirect(URL('cardapio', 'listar_cardapio_mobile'))
        else:
            response.flash = "CPF ou Data de Nascimento inválidos."
            return dict(form=FORM(INPUT(_name='cpf', _placeholder='CPF', _class='form-control'),
                                  INPUT(_name='birth_date', _placeholder='Data de Nascimento', _type='date', _class='form-control'),
                                  INPUT(_type='submit', _value='Entrar', _class='btn btn-primary')))
    else:
        form = FORM(INPUT(_name='cpf', _placeholder='CPF', _class='form-control'),
                    INPUT(_name='birth_date', _placeholder='Data de Nascimento', _type='date', _class='form-control'),
                    INPUT(_type='submit', _value='Entrar', _class='btn btn-primary'))

        return dict(form=form)









def logs():
    """
    Página principal de auditoria com filtros
    """
    # Obtém listas para os filtros
    entidades = db().select(db.log_sistema.entidade, distinct=True)
    entidades_list = [row.entidade for row in entidades]
    
    usuarios = db().select(db.auth_user.id, db.auth_user.first_name, db.auth_user.last_name, orderby=db.auth_user.first_name)
    acoes = ['exclusao', 'edicao']
    
    # Inicializa os filtros
    filtro_entidade = request.vars.entidade
    filtro_usuario = request.vars.usuario
    filtro_acao = request.vars.acao
    filtro_data_inicio = request.vars.data_inicio
    filtro_data_fim = request.vars.data_fim
    
    # Constrói a consulta com os filtros
    query = (db.log_sistema.id > 0)
    
    if filtro_entidade:
        query &= (db.log_sistema.entidade == filtro_entidade)
    
    # Modificando a pesquisa de usuário para usar LIKE em vez de igualdade
    if filtro_usuario:
        # Primeiro precisamos encontrar os usuários cujos nomes correspondem parcialmente
        termo_busca = '%' + filtro_usuario.lower() + '%'
        subquery = db((db.auth_user.first_name.lower().like(termo_busca)) | 
                      (db.auth_user.last_name.lower().like(termo_busca)))._select(db.auth_user.id)
        # Agora filtramos logs por esses usuários
        query &= (db.log_sistema.user_id.belongs(subquery))
    
    if filtro_acao:
        query &= (db.log_sistema.acao == filtro_acao)
    
    if filtro_data_inicio:
        data_inicio = datetime.datetime.strptime(filtro_data_inicio, '%Y-%m-%d')
        query &= (db.log_sistema.dataH >= data_inicio)
    
    if filtro_data_fim:
        data_fim = datetime.datetime.strptime(filtro_data_fim, '%Y-%m-%d') + datetime.timedelta(days=1)
        query &= (db.log_sistema.dataH < data_fim)
    
    # Paginação
    pagina = request.vars.page or 1
    pagina = int(pagina)
    itens_por_pagina = 15
    limitby = ((pagina - 1) * itens_por_pagina, pagina * itens_por_pagina)
    
    # Consulta no banco
    registros = db(query).select(
        db.log_sistema.ALL,
        db.auth_user.first_name,
        db.auth_user.last_name,
        left=db.auth_user.on(db.log_sistema.user_id == db.auth_user.id),
        orderby=~db.log_sistema.dataH,
        limitby=limitby
    )
    
    total_registros = db(query).count()
    total_paginas = (total_registros + itens_por_pagina - 1) // itens_por_pagina
    
    # Retorna para a view
    return dict(
        registros=registros,
        entidades_list=entidades_list,
        usuarios=usuarios,
        acoes=acoes,
        filtro_entidade=filtro_entidade,
        filtro_usuario=filtro_usuario,
        filtro_acao=filtro_acao,
        filtro_data_inicio=filtro_data_inicio,
        filtro_data_fim=filtro_data_fim,
        pagina=pagina,
        total_paginas=total_paginas
    )

def detalhes():
    """
    Exibe detalhes de um log específico
    """
    log_id = request.args(0)
    if not log_id:
        redirect(URL('index'))
    
    log = db(db.log_sistema.id == log_id).select().first()
    if not log:
        session.flash = 'Registro de log não encontrado'
        redirect(URL('index'))
    
    # Buscar informações adicionais dependendo da entidade
    entidade_info = None
    if log.entidade == 'cardapio':
        entidade_info = db(db.cardapio.id == log.registro_id).select().first()
    elif log.entidade == 'estoque':
        entidade_info = db(db.estoque.id == log.registro_id).select().first()
    elif log.entidade == 'user':
        entidade_info = db(db.auth_user.id == log.registro_id).select().first()
    
    # Buscar informações do usuário que realizou a ação
    usuario = db(db.auth_user.id == log.user_id).select().first()
    
    return dict(log=log, entidade_info=entidade_info, usuario=usuario)

def exportar_csv():
    """
    Exporta os logs filtrados para CSV
    """
    # Obter os mesmos filtros da página principal
    filtro_entidade = request.vars.entidade
    filtro_usuario = request.vars.usuario
    filtro_acao = request.vars.acao
    filtro_data_inicio = request.vars.data_inicio
    filtro_data_fim = request.vars.data_fim
    
    query = (db.log_sistema.id > 0)
    
    if filtro_entidade:
        query &= (db.log_sistema.entidade == filtro_entidade)
    
    if filtro_usuario:
        query &= (db.log_sistema.user_id == filtro_usuario)
    
    if filtro_acao:
        query &= (db.log_sistema.acao == filtro_acao)
    
    if filtro_data_inicio:
        data_inicio = datetime.datetime.strptime(filtro_data_inicio, '%Y-%m-%d')
        query &= (db.log_sistema.dataH >= data_inicio)
    
    if filtro_data_fim:
        data_fim = datetime.datetime.strptime(filtro_data_fim, '%Y-%m-%d') + datetime.timedelta(days=1)
        query &= (db.log_sistema.dataH < data_fim)
    
    # Buscar todos os registros que correspondem aos filtros
    registros = db(query).select(
        db.log_sistema.id,
        db.log_sistema.entidade,
        db.log_sistema.acao,
        db.log_sistema.registro_id,
        db.log_sistema.dataH,
        db.auth_user.first_name,
        db.auth_user.last_name,
        left=db.auth_user.on(db.log_sistema.user_id == db.auth_user.id),
        orderby=~db.log_sistema.dataH
    )
    
    # Preparar o arquivo CSV
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Cabeçalho
    writer.writerow(['ID', 'Entidade', 'Ação', 'ID do Registro', 'Data e Hora', 'Usuário'])
    
    # Dados
    for registro in registros:
        nome_usuario = f"{registro.auth_user.first_name} {registro.auth_user.last_name}" if registro.auth_user else "N/A"
        writer.writerow([
            registro.log_sistema.id,
            registro.log_sistema.entidade,
            registro.log_sistema.acao,
            registro.log_sistema.registro_id,
            registro.log_sistema.dataH.strftime('%d/%m/%Y %H:%M:%S'),
            nome_usuario
        ])
    
    # Configurar a resposta
    response.headers['Content-Type'] = 'text/csv'
    filename = f'auditoria_logs_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    
    return output.getvalue()

import json as pyjson  # Importamos como pyjson para evitar conflito com o Web2py

def detalhesLog():
    """
    Exibe detalhes de um log específico
    """
    log_id = request.args(0)
    if not log_id:
        redirect(URL('index'))
    
    log = db(db.log_sistema.id == log_id).select().first()
    if not log:
        session.flash = 'Registro de log não encontrado'
        redirect(URL('index'))
    
    # Buscar informações adicionais dependendo da entidade
    entidade_info = None
    if log.entidade == 'cardapio':
        entidade_info = db(db.cardapio.id == log.registro_id).select().first()
    elif log.entidade == 'estoque':
        entidade_info = db(db.estoque.id == log.registro_id).select().first()
    elif log.entidade == 'user':
        entidade_info = db(db.auth_user.id == log.registro_id).select().first()
    
    # Buscar informações do usuário que realizou a ação
    usuario = db(db.auth_user.id == log.user_id).select().first()
    
    return dict(log=log, entidade_info=entidade_info, usuario=usuario)


def log_details():
    log_id = request.vars.id
    log = db.log_sistema(log_id) or redirect(URL('logs'))

    # Verifica se o campo observacao é string ou dict
    if isinstance(log.observacao, str):
        observacao = pyjson.loads(log.observacao)  # Carrega JSON caso seja string
    elif isinstance(log.observacao, dict):
        observacao = log.observacao  # Já é um dicionário Python
    else:
        observacao = {}  # Valor padrão para observação ausente ou inválida

    return response.json(dict(
        user=log.user_id.first_name,
        entidade=log.entidade,
        acao=log.acao,
        registro_id=log.registro_id,
        observacao=observacao,
        dataH=log.dataH
    ))



def registrar_log(entidade, registro_id, acao, estado_anterior=None):
    """Registra uma ação no log geral do sistema.

    Args:
        entidade (str): Nome da entidade afetada (ex: 'estoque', 'auth_user').
        registro_id (int): ID do registro afetado na entidade.
        acao (str): Tipo de ação ('exclusao' ou 'alteracao').
        estado_anterior (dict, opcional): Estado anterior do registro, caso seja uma alteração.
    """
    db.log_sistema.insert(
        user_id=auth.user_id,
        entidade=entidade,
        acao=acao,
        registro_id=registro_id,
        observacao=estado_anterior,
        timestamp=request.now
    )
    db.commit()


@auth.requires_login()
def index():
    return dict()



@auth.requires_login()
def api_detalhes_usuarios_por_tipo_refeicao():
    """
    API para retornar detalhes individuais dos usuários por tipo de refeição
    """
    try:
        # Obter tipo de refeição específico
        tipo_refeicao_detalhes = request.vars.tipo_refeicao_detalhes
        if not tipo_refeicao_detalhes:
            raise ValueError("Tipo de refeição não especificado")

        # Aplicar os mesmos filtros da página principal
        filtro_nome = request.vars.nome or ""
        filtro_tipo_usuario = request.vars.tipo_usuario or ""
        filtro_setor = request.vars.setor or ""
        filtro_tipo_refeicao = request.vars.tipo_refeicao
        filtro_nome_prato = request.vars.nome_prato or ""
        data_inicio = request.vars.data_inicio or None
        data_fim = request.vars.data_fim or None

        # Query base
        query = (db.solicitacao_refeicao.id > 0)

        # Filtro por tipo de refeição específico
        if tipo_refeicao_detalhes == "A la carte":
            query &= db.cardapio.tipo.belongs(["A la carte", "Livre"])
        else:
            query &= (db.cardapio.tipo == tipo_refeicao_detalhes)

        # Aplicar outros filtros
        if filtro_nome:
            query &= db.auth_user.first_name.contains(filtro_nome)
        if filtro_nome_prato:
            query &= db.cardapio.nome.contains(filtro_nome_prato)
        
        # Filtro por tipo de usuário
        if filtro_tipo_usuario:
            if filtro_tipo_usuario == "Colaboradores Generalizados":
                user_types = db(db.user_type.name.belongs(['colaborador', 'medico', 'gestor', 'administrador', 'instrumentador'])).select(db.user_type.id)
                user_type_ids = [ut.id for ut in user_types]
                setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
                setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None
                if setor_colaborador_hemodialise_id:
                    tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
                    tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None
                    query &= ((db.auth_user.user_type.belongs(user_type_ids)) |
                              ((db.auth_user.setor_id == setor_colaborador_hemodialise_id) & (db.auth_user.user_type == tipo_hemodialise_id)))
            elif filtro_tipo_usuario == "Pacientes Generalizados":
                user_types = db(db.user_type.name.belongs(['paciente', 'paciente convenio', 'acompanhante', 'hemodialise'])).select(db.user_type.id)
                user_type_ids = [ut.id for ut in user_types]
                setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodiálise").select(db.setor.id).first()
                setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None
                tipo_hemodialise = db(db.user_type.name == "hemodialise").select(db.user_type.id).first()
                tipo_hemodialise_id = tipo_hemodialise.id if tipo_hemodialise else None
                query &= db.auth_user.user_type.belongs(user_type_ids)
                if setor_colaborador_hemodialise_id:
                    query &= ~((db.auth_user.user_type == tipo_hemodialise_id) &
                               (db.auth_user.setor_id == setor_colaborador_hemodialise_id))
            else:
                user_type = db(db.user_type.name == filtro_tipo_usuario).select(db.user_type.id).first()
                if user_type:
                    query &= (db.auth_user.user_type == user_type.id)

        if filtro_setor:
            query &= (db.auth_user.setor_id == int(filtro_setor))
        if data_inicio:
            query &= (db.solicitacao_refeicao.data_solicitacao >= data_inicio)
        if data_fim:
            query &= (db.solicitacao_refeicao.data_solicitacao <= data_fim)
        if filtro_tipo_refeicao == "especial":
            query &= (db.cardapio.tipo.belongs(["Livre", "A la carte", "Bebidas"]))
        elif filtro_tipo_refeicao == "comum":
            query &= (db.cardapio.tipo.belongs(['Almoço', 'Café da Manhã', 'Ceia', 'Lanche', 'Jantar']))

        # Buscar dados agrupados por usuário
        usuarios_detalhes = db(query).select(
            db.auth_user.first_name.with_alias('nome_usuario'),
            db.user_type.name.with_alias('tipo_usuario'),
            db.setor.name.with_alias('setor'),
            db.solicitacao_refeicao.id.count().with_alias('total_pedidos'),
            db.solicitacao_refeicao.quantidade_solicitada.sum().with_alias('total_unidades'),
            db.solicitacao_refeicao.preco.sum().with_alias('total_gasto'),
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.user_type.on(db.auth_user.user_type == db.user_type.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ],
            groupby=[db.auth_user.first_name, db.user_type.name, db.setor.name],
            orderby=~db.solicitacao_refeicao.preco.sum()
        )

        # Processar dados
        dados_usuarios = []
        total_usuarios = 0
        receita_total = 0

        for usuario in usuarios_detalhes:
            total_gasto = float(usuario.total_gasto or 0)
            total_pedidos = int(usuario.total_pedidos or 0)
            media_pedido = total_gasto / total_pedidos if total_pedidos > 0 else 0
            
            dados_usuarios.append({
                'nome_usuario': usuario.nome_usuario,
                'tipo_usuario': usuario.tipo_usuario or 'Sem tipo',
                'setor': usuario.setor or 'Sem setor',
                'total_pedidos': total_pedidos,
                'total_unidades': int(usuario.total_unidades or 0),
                'total_gasto': total_gasto,
                'media_por_pedido': media_pedido
            })
            
            total_usuarios += 1
            receita_total += total_gasto

        return response.json({
            'status': 'success',
            'tipo_refeicao': tipo_refeicao_detalhes,
            'usuarios': dados_usuarios,
            'resumo': {
                'total_usuarios': total_usuarios,
                'receita_total': receita_total
            }
        })

    except Exception as e:
        import traceback
        return response.json({
            'status': 'error',
            'message': str(e),
            'debug': traceback.format_exc() if request.is_local else None
        })


