# controllers/admin.py
import json

@auth.requires_login()
def index():
    """
    Exibe e permite editar as configurações do sistema.
    """
    # Verifica se o usuário tem permissão
    if not (auth.has_membership(role='Administrador') or auth.has_membership(role='Gestor')):
        session.flash = 'Acesso negado. Você precisa ser um administrador para acessar essa página.'
        redirect(URL('default', 'index'))
    
    # Parâmetros de paginação
    pagina = int(request.vars.pagina or 1)
    registros_por_pagina = 10
    inicio = (pagina - 1) * registros_por_pagina
    
    # Busca todas as configurações com paginação
    configuracoes = db(db.configuracoes.id > 0).select(
        orderby=db.configuracoes.nome,
        limitby=(inicio, inicio + registros_por_pagina)
    )
    
    # Busca todos os tipos de usuário para os checkboxes
    tipos_usuario = []
    try:
        # Obtém tipos de usuário diretamente do banco
        user_types = db(db.user_type.id > 0).select(db.user_type.name, orderby=db.user_type.name)
        tipos_usuario = [ut.name for ut in user_types]
    except Exception as e:
        import sys
        print(f"Erro ao obter tipos de usuário: {e}", file=sys.stderr)
    
    # Busca todos os tipos de refeição para os checkboxes
    tipos_refeicao = []
    try:
        # Obtém tipos de refeição diretamente do banco
        refeicoes = db(db.horario_refeicoes.id > 0).select(
            db.horario_refeicoes.refeicao, 
            distinct=True,
            orderby=db.horario_refeicoes.refeicao
        )
        tipos_refeicao = [r.refeicao for r in refeicoes]
    except Exception as e:
        import sys
        print(f"Erro ao obter tipos de refeição: {e}", file=sys.stderr)
    
    # Total de registros para paginação
    total_configuracoes = db(db.configuracoes.id > 0).count()
    total_paginas = (total_configuracoes // registros_por_pagina) + (1 if total_configuracoes % registros_por_pagina > 0 else 0)
    
    return dict(
        configuracoes=configuracoes,
        tipos_usuario=tipos_usuario,
        tipos_refeicao=tipos_refeicao,
        pagina=pagina,
        total_paginas=total_paginas
    )

@auth.requires_login()
def api_atualizar_configuracao():
    """
    API para atualizar uma configuração existente.
    """
    # Verifica se o usuário tem permissão
    if not (auth.has_membership(role='Administrador') or auth.has_membership(role='Gestor')):
        return response.json({'status': 'error', 'message': 'Acesso negado. Você precisa ser um administrador.'})
    
    try:
        # Obter dados JSON da requisição
        import json
        import sys
        
        # Log para depuração
        print("Recebendo requisição de atualização de configuração", file=sys.stderr)
        
        data = request.body.read().decode('utf-8')
        print(f"Dados brutos recebidos: {data[:500]}", file=sys.stderr)
        
        # Análise do JSON
        try:
            dados = json.loads(data)
            print(f"Dados JSON processados: {json.dumps(dados)[:500]}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Erro ao decodificar JSON: {str(e)}", file=sys.stderr)
            return response.json({'status': 'error', 'message': f'JSON inválido: {str(e)}'})
        
        # Validação básica
        if not dados.get('id') or 'valor' not in dados:
            print("Parâmetros obrigatórios não fornecidos", file=sys.stderr)
            return response.json({'status': 'error', 'message': 'Parâmetros obrigatórios não fornecidos.'})
        
        config_id = dados.get('id')
        tipo = dados.get('tipo')
        valor = dados.get('valor')
        descricao = dados.get('descricao', "")
        
        print(f"Processando atualização: ID={config_id}, Tipo={tipo}", file=sys.stderr)
        print(f"Valor recebido: {valor[:1000]}", file=sys.stderr)
        
        # Verifica se a configuração existe
        config = db.configuracoes(config_id)
        if not config:
            print(f"Configuração não encontrada: ID={config_id}", file=sys.stderr)
            return response.json({'status': 'error', 'message': 'Configuração não encontrada.'})
        
        print(f"Configuração encontrada: {config.nome}", file=sys.stderr)
        
        # Salva o estado anterior para o log
        estado_anterior = {
            'nome': config.nome,
            'valor': config.valor,
            'tipo': config.tipo,
            'descricao': config.descricao
        }
        
        # Validação e formatação do valor com base no tipo
        if tipo == 'int':
            try:
                valor = int(valor)
                print(f"Valor convertido para inteiro: {valor}", file=sys.stderr)
            except ValueError:
                print("Erro: o valor não é um número inteiro válido", file=sys.stderr)
                return response.json({'status': 'error', 'message': 'O valor deve ser um número inteiro.'})
        elif tipo == 'float':
            try:
                valor = float(valor)
                print(f"Valor convertido para float: {valor}", file=sys.stderr)
            except ValueError:
                print("Erro: o valor não é um número decimal válido", file=sys.stderr)
                return response.json({'status': 'error', 'message': 'O valor deve ser um número decimal.'})
        elif tipo == 'boolean':
            if valor.lower() not in ['true', 'false']:
                print("Erro: o valor booleano deve ser 'true' ou 'false'", file=sys.stderr)
                return response.json({'status': 'error', 'message': 'O valor deve ser "true" ou "false".'})
            valor = valor.lower()
            print(f"Valor booleano: {valor}", file=sys.stderr)
        elif tipo == 'json':
            print("Processando valor JSON...", file=sys.stderr)
            
            # Verificar se o valor é uma string JSON válida
            try:
                # Tentativa de parse do JSON
                json_obj = json.loads(valor)
                print(f"JSON processado com sucesso. Tipo: {type(json_obj)}", file=sys.stderr)
                print(f"Conteúdo JSON: {json.dumps(json_obj)[:500]}", file=sys.stderr)
                
                # Validações específicas para configurações baseadas em tipos de usuário ou refeição
                if config.nome == 'tipos_prato_sem_gratuidade':
                    print("Validando tipos de refeição...", file=sys.stderr)
                    if not isinstance(json_obj, list):
                        print("Erro: não é uma lista de tipos de refeição", file=sys.stderr)
                        return response.json({
                            'status': 'error', 
                            'message': 'O valor deve ser uma lista de tipos de refeição'
                        })
                
                elif 'tipos_usuario' in config.nome:
                    print("Validando tipos de usuário...", file=sys.stderr)
                    if not isinstance(json_obj, list):
                        print("Erro: não é uma lista de tipos de usuário", file=sys.stderr)
                        return response.json({
                            'status': 'error', 
                            'message': 'O valor deve ser uma lista de tipos de usuário'
                        })
                
                # Mantemos o valor como está, já que ele é uma string JSON válida
                print(f"Valor final JSON: {valor[:500]}", file=sys.stderr)
                
            except json.JSONDecodeError as e:
                print(f"Erro ao decodificar JSON do valor: {str(e)}", file=sys.stderr)
                return response.json({'status': 'error', 'message': f'Formato JSON inválido no valor: {str(e)}'})
        
        print(f"Valor final após processamento: {valor if isinstance(valor, (int, float, bool)) else valor[:500]}", file=sys.stderr)
        
        # Atualiza a configuração
        try:
            config.update_record(
                valor=valor,
                descricao=descricao
            )
            print("Registro atualizado com sucesso", file=sys.stderr)
            
        except Exception as update_error:
            print(f"Erro ao atualizar o registro: {str(update_error)}", file=sys.stderr)
            db.rollback()
            return response.json({'status': 'error', 'message': f'Erro ao atualizar o registro: {str(update_error)}'})
        
        # Registra log da ação
        try:
            registrar_log(
                entidade='configuracoes',
                registro_id=config_id,
                acao='edicao',
                estado_anterior=estado_anterior
            )
            print("Log registrado com sucesso", file=sys.stderr)
        except Exception as log_error:
            # Não interrompe o fluxo se o registro de log falhar
            print(f"Erro ao registrar log: {str(log_error)}", file=sys.stderr)
        
        # Commit das alterações
        try:
            db.commit()
            print("Commit realizado com sucesso", file=sys.stderr)
        except Exception as commit_error:
            print(f"Erro no commit: {str(commit_error)}", file=sys.stderr)
            db.rollback()
            return response.json({'status': 'error', 'message': f'Erro ao salvar as alterações: {str(commit_error)}'})
        
        print("Operação concluída com sucesso", file=sys.stderr)
        return response.json({
            'status': 'success',
            'message': 'Configuração atualizada com sucesso!'
        })
        
    except Exception as e:
        db.rollback()
        import sys, traceback
        print("Erro geral na API:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return response.json({'status': 'error', 'message': str(e)})
    





@auth.requires_membership('Administrador')
def gerenciar_categorias():
    """Permite a configuração das categorias de usuários de forma personalizada"""
    # Busca todas as categorias ordenadas pelo nome
    categorias = db(db.categoria_usuario).select(orderby=db.categoria_usuario.nome)
    
    return dict(categorias=categorias)

@auth.requires_membership('Administrador')
def adicionar_categoria():
    """Adiciona uma nova categoria de usuário"""
    nome = request.vars.nome
    descricao = request.vars.descricao
    
    if not nome:
        session.flash = "Nome da categoria é obrigatório"
        redirect(URL('gerenciar_categorias'))
    
    # Verifica se já existe uma categoria com este nome
    if db(db.categoria_usuario.nome == nome).count() > 0:
        session.flash = "Já existe uma categoria com este nome"
        redirect(URL('gerenciar_categorias'))
    
    # Insere a nova categoria
    db.categoria_usuario.insert(nome=nome, descricao=descricao)
    session.flash = "Categoria adicionada com sucesso"
    redirect(URL('gerenciar_categorias'))

@auth.requires_membership('Administrador')
def excluir_categoria():
    """Remove uma categoria existente"""
    categoria_id = request.args(0)
    
    if not categoria_id:
        session.flash = "Categoria não especificada"
        redirect(URL('gerenciar_categorias'))
    
    # Removemos a verificação de usuários associados que estava causando o erro
    # Se você quiser verificar dependências, precisaria adaptar esta parte para
    # usar o campo correto da sua tabela auth_user que armazena a categoria
    
    # Exclui a categoria
    db(db.categoria_usuario.id == categoria_id).delete()
    session.flash = "Categoria excluída com sucesso"
    redirect(URL('gerenciar_categorias'))

@auth.requires_membership('Administrador')
def atualizar_categoria():
    """Atualiza os dados de uma categoria existente"""
    categoria_id = request.vars.id
    nome = request.vars.nome
    descricao = request.vars.descricao
    
    if not categoria_id or not nome:
        session.flash = "Dados incompletos para atualização"
        redirect(URL('gerenciar_categorias'))
    
    # Verifica se já existe outra categoria com este nome
    duplicada = db((db.categoria_usuario.nome == nome) & 
                  (db.categoria_usuario.id != categoria_id)).count()
    if duplicada > 0:
        session.flash = "Já existe outra categoria com este nome"
        redirect(URL('gerenciar_categorias'))
    
    # Atualiza a categoria
    db(db.categoria_usuario.id == categoria_id).update(
        nome=nome,
        descricao=descricao
    )
    session.flash = "Categoria atualizada com sucesso"
    redirect(URL('gerenciar_categorias'))

@auth.requires_membership('Administrador')
def gerenciar_tipos_categoria():
    """Permite associar tipos de usuário às categorias"""
    categoria_id = request.args(0)
    if not categoria_id:
        redirect(URL('gerenciar_categorias'))
    
    categoria = db.categoria_usuario(categoria_id)
    if not categoria:
        redirect(URL('gerenciar_categorias'))
    
    # Listar tipos já associados
    tipos_associados = db(db.categoria_tipo_usuario.categoria_id == categoria_id).select(
        db.user_type.ALL,
        left=db.user_type.on(db.categoria_tipo_usuario.tipo_id == db.user_type.id)
    )
    
    # Listar todos os tipos para seleção
    todos_tipos = db(db.user_type).select(orderby=db.user_type.name)
    
    # Pré-processar quais tipos ainda estão disponíveis para associar
    tipos_disponiveis = []
    ids_associados = [tipo.id for tipo in tipos_associados]
    
    for tipo in todos_tipos:
        if tipo.id not in ids_associados:
            tipos_disponiveis.append(tipo)
    
    return dict(
        categoria=categoria,
        tipos_associados=tipos_associados,
        todos_tipos=todos_tipos,
        tipos_disponiveis=tipos_disponiveis
    )

@auth.requires_membership('Administrador')
def adicionar_tipo_categoria():
    """Adiciona um tipo à categoria especificada"""
    categoria_id = request.args(0)
    tipo_id = request.vars.tipo_id
    
    if not categoria_id or not tipo_id:
        session.flash = "Dados incompletos para adicionar tipo à categoria"
        redirect(URL('gerenciar_categorias'))
    
    # Verificar se a categoria existe
    categoria = db.categoria_usuario(categoria_id)
    if not categoria:
        session.flash = "Categoria não encontrada"
        redirect(URL('gerenciar_categorias'))
    
    # Verificar se o tipo existe
    tipo = db.user_type(tipo_id)
    if not tipo:
        session.flash = "Tipo de usuário não encontrado"
        redirect(URL('gerenciar_tipos_categoria', args=[categoria_id]))
    
    # Verificar se a associação já existe
    existe = db((db.categoria_tipo_usuario.categoria_id == categoria_id) & 
                (db.categoria_tipo_usuario.tipo_id == tipo_id)).count()
    if existe > 0:
        session.flash = "Este tipo já está associado a esta categoria"
        redirect(URL('gerenciar_tipos_categoria', args=[categoria_id]))
    
    # Adicionar a associação
    db.categoria_tipo_usuario.insert(
        categoria_id=categoria_id,
        tipo_id=tipo_id
    )
    
    session.flash = "Tipo adicionado à categoria com sucesso"
    redirect(URL('gerenciar_tipos_categoria', args=[categoria_id]))

@auth.requires_membership('Administrador')
def remover_tipo_categoria():
    """Remove um tipo da categoria especificada"""
    categoria_id = request.args(0)
    tipo_id = request.args(1)
    
    if not categoria_id or not tipo_id:
        session.flash = "Dados incompletos para remover tipo da categoria"
        redirect(URL('gerenciar_categorias'))
    
    # Remover a associação
    db((db.categoria_tipo_usuario.categoria_id == categoria_id) & 
       (db.categoria_tipo_usuario.tipo_id == tipo_id)).delete()
    
    session.flash = "Tipo removido da categoria com sucesso"
    redirect(URL('gerenciar_tipos_categoria', args=[categoria_id]))


@auth.requires_membership('Administrador')
def gerenciar_setores_por_tipo():
    """Permite configurar quais setores são permitidos para cada tipo de usuário"""
    tipo_id = request.args(0)
    
    # Sempre buscar todos os tipos para o dropdown, independente da rota
    tipos = db(db.user_type).select(orderby=db.user_type.name)
    
    if not tipo_id:
        # Mostrar lista de tipos para selecionar
        return dict(tipos=tipos, tipo=None)
    
    # Buscar o tipo de usuário selecionado
    tipo = db.user_type(tipo_id) or redirect(URL('gerenciar_setores_por_tipo'))
    
    # Criar um formulário para adicionar setores ao tipo
    form = SQLFORM(db.tipo_usuario_setor)
    form.vars.tipo_id = tipo_id
    
    if form.process(onvalidation=lambda form: validar_setor_tipo(form, tipo_id)).accepted:
        response.flash = 'Setor adicionado ao tipo com sucesso!'
        # Atualizar a configuração
        atualizar_configuracao_setores_por_tipo()
        # Redirecionar para atualizar a página sem reenvio de formulário
        redirect(URL('gerenciar_setores_por_tipo', args=[tipo_id]))
    
    # Buscar IDs dos setores associados
    ids_setores = [r.setor_id for r in db(db.tipo_usuario_setor.tipo_id == tipo_id).select(db.tipo_usuario_setor.setor_id)]
    
    # Buscar detalhes dos setores
    setores_associados = db(db.setor.id.belongs(ids_setores)).select() if ids_setores else []
    
    # Listar todos os setores para seleção
    todos_setores = db(db.setor).select(orderby=db.setor.name)
    
    return dict(
        tipo=tipo, 
        form=form, 
        setores_associados=setores_associados,
        todos_setores=todos_setores,
        tipos=tipos  # Adicionar a lista de tipos a todas as rotas
    )

def validar_setor_tipo(form, tipo_id):
    """Valida se a associação tipo-setor já existe"""
    setor_id = form.vars.setor_id
    
    # Verificar se já existe essa associação
    if db((db.tipo_usuario_setor.tipo_id == tipo_id) & 
          (db.tipo_usuario_setor.setor_id == setor_id)).count():
        form.errors.setor_id = 'Este setor já está associado a este tipo de usuário'
        return False
    
    return True
def validar_setor_tipo(form, tipo_id):
    """Valida se a associação tipo-setor já existe"""
    setor_id = form.vars.setor_id
    
    # Verificar se já existe essa associação
    if db((db.tipo_usuario_setor.tipo_id == tipo_id) & 
          (db.tipo_usuario_setor.setor_id == setor_id)).count():
        form.errors.setor_id = 'Este setor já está associado a este tipo de usuário'
        return False
    
    return True

@auth.requires_membership('Administrador')
def remover_tipo_categoria():
    """Remove um tipo de usuário de uma categoria"""
    categoria_id = request.args(0)
    tipo_id = request.args(1)
    
    if not categoria_id or not tipo_id:
        redirect(URL('gerenciar_categorias'))
    
    # Verificar se a categoria e o tipo existem
    categoria = db.categoria_usuario(categoria_id)
    tipo = db.user_type(tipo_id)
    
    if not categoria or not tipo:
        session.flash = 'Categoria ou tipo não encontrado.'
        redirect(URL('gerenciar_categorias'))
    
    # Remover a associação
    db((db.categoria_tipo_usuario.categoria_id == categoria_id) & 
       (db.categoria_tipo_usuario.tipo_id == tipo_id)).delete()
    
    session.flash = f'Tipo "{tipo.name}" removido da categoria "{categoria.nome}" com sucesso!'
    redirect(URL('gerenciar_tipos_categoria', args=[categoria_id]))

@auth.requires_membership('Administrador')
def remover_setor_tipo():
    """Remove um setor de um tipo de usuário"""
    tipo_id = request.args(0)
    setor_id = request.args(1)
    
    if not tipo_id or not setor_id:
        redirect(URL('gerenciar_setores_por_tipo'))
    
    # Verificar se o tipo e o setor existem
    tipo = db.user_type(tipo_id)
    setor = db.setor(setor_id)
    
    if not tipo or not setor:
        session.flash = 'Tipo ou setor não encontrado.'
        redirect(URL('gerenciar_setores_por_tipo'))
    
    # Remover a associação
    db((db.tipo_usuario_setor.tipo_id == tipo_id) & 
       (db.tipo_usuario_setor.setor_id == setor_id)).delete()
    
    session.flash = f'Setor "{setor.name}" removido do tipo "{tipo.name}" com sucesso!'
    redirect(URL('gerenciar_setores_por_tipo', args=[tipo_id]))

@auth.requires_membership('Administrador')
def inicializar_categorias():
    """Inicializa as categorias padrão e suas associações"""
    
    # Verifica se já existem categorias
    if db(db.categoria_usuario.id > 0).count() == 0:
        # Criar categorias padrão
        categorias = [
            {
                'nome': 'Pacientes',
                'descricao': 'Usuários que são pacientes (internados, ambulatoriais, etc)',
                'cor': '#007bff'
            },
            {
                'nome': 'Colaboradores',
                'descricao': 'Funcionários e profissionais do hospital',
                'cor': '#28a745'
            },
            {
                'nome': 'Acompanhantes',
                'descricao': 'Acompanhantes de pacientes',
                'cor': '#17a2b8'
            }
        ]
        
        categoria_ids = {}
        for cat in categorias:
            categoria_ids[cat['nome']] = db.categoria_usuario.insert(**cat)
        
        # Mapeamento de tipos para categorias
        mapeamento = {
            'Pacientes': ['Paciente', 'Paciente Convenio', 'Paciente Particular'],
            'Colaboradores': ['Hemodiálise', 'Instrumentador', 'Gestor', 'Colaborador', 'Medico', 'Administrador'],
            'Acompanhantes': ['Acompanhante']
        }
        
        # Associar tipos às categorias
        for categoria_nome, tipos_nomes in mapeamento.items():
            if categoria_nome in categoria_ids:
                categoria_id = categoria_ids[categoria_nome]
                
                # Buscar tipos por nome
                for tipo_nome in tipos_nomes:
                    tipo = db(db.user_type.name == tipo_nome).select().first()
                    if tipo:
                        # Verificar se já existe a associação
                        if not db((db.categoria_tipo_usuario.categoria_id == categoria_id) & 
                                (db.categoria_tipo_usuario.tipo_id == tipo.id)).count():
                            db.categoria_tipo_usuario.insert(
                                categoria_id=categoria_id,
                                tipo_id=tipo.id
                            )
        
        # Inicializar mapeamento de setores por tipo
        setores_por_tipo = {
            "3": ["Administrativo"],  # "Gestor"
            "9": ["Hemodialise", "Colaborador Hemodialise"],  # "Hemodialise"
            "10": ["Medico"],  # "Medico"
            "5": ["Instrumentador"],  # "Instrumentador"
            "2": [
                "Recepção", "Serviços Gerais", "Faturamento",
                "Cozinha", "Enfermagem", "Radiologia", "Nutrição",
                "Hemodialise", "Centro Cirurgico", "Consultorio Particular",
                "U.T.I", "Lavanderia"
            ]  # "Colaborador"
        }
        
        # Criar associações de tipo-setor
        for tipo_id_str, setores_nomes in setores_por_tipo.items():
            tipo_id = int(tipo_id_str)
            for setor_nome in setores_nomes:
                setor = db(db.setor.name == setor_nome).select().first()
                if setor:
                    if not db((db.tipo_usuario_setor.tipo_id == tipo_id) & 
                            (db.tipo_usuario_setor.setor_id == setor.id)).count():
                        db.tipo_usuario_setor.insert(
                            tipo_id=tipo_id,
                            setor_id=setor.id
                        )
        
        # Salvar o mapeamento de setores por tipo na configuração
        setor_names = {}
        for tipo in db(db.user_type).select():
            setores_do_tipo = db(db.tipo_usuario_setor.tipo_id == tipo.id).select(
                db.setor.name,
                left=db.setor.on(db.tipo_usuario_setor.setor_id == db.setor.id)
            )
            setor_names[str(tipo.id)] = [s.name for s in setores_do_tipo]
        
        # Criar configuração
        db.configuracoes.update_or_insert(
            db.configuracoes.nome == 'setores_por_tipo_colaborador',
            nome='setores_por_tipo_colaborador',
            valor=json.dumps(setor_names),
            descricao='Mapeamento de tipos de usuário para seus setores permitidos',
            tipo='json'
        )
        
        db.commit()
        return dict(
            mensagem="Categorias e associações inicializadas com sucesso!",
            categorias=categorias,
            mapeamento=mapeamento
        )
    else:
        return dict(
            mensagem="As categorias já foram inicializadas anteriormente.",
            categorias=db(db.categoria_usuario).select()
        )
    
def atualizar_configuracao_setores_por_tipo():
    """
    Atualiza a configuração de setores por tipo após alterações nas associações.
    Esta função é chamada após adicionar ou remover associações.
    """
    # Construir o mapeamento de tipos para setores
    setor_names = {}
    for tipo in db(db.user_type).select():
        setores_do_tipo = db(db.tipo_usuario_setor.tipo_id == tipo.id).select(
            db.setor.name,
            left=db.setor.on(db.tipo_usuario_setor.setor_id == db.setor.id)
        )
        setor_names[str(tipo.id)] = [s.name for s in setores_do_tipo if s.name]
    
    # Atualizar ou criar a configuração
    config_setores = db(db.configuracoes.nome == 'setores_por_tipo_colaborador').select().first()
    if config_setores:
        config_setores.update_record(valor=json.dumps(setor_names))
    else:
        db.configuracoes.insert(
            nome='setores_por_tipo_colaborador',
            valor=json.dumps(setor_names),
            descricao='Mapeamento de tipos de usuário para seus setores permitidos',
            tipo='json'
        )
    
    db.commit()

def migrar_setores_para_db():

    """
    Função para migrar os setores permitidos do JavaScript para o banco de dados.
    Execute esta função uma vez para inicializar a tabela tipo_usuario_setor.
    """
    # Mapeamento atual (do JavaScript)
    setores_hardcoded = {
        "3": ["Administrativo"],  # "Gestor"
        "9": ["Hemodialise", "Colaborador Hemodialise"],  # "Hemodialise"
        "10": ["Medico"],  # "Medico"
        "5": ["Instrumentador"],  # "Instrumentador"
        "2": [
            "Recepção",
            "Serviços Gerais",
            "Faturamento",
            "Cozinha",
            "Enfermagem",
            "Radiologia",
            "Nutrição",
            "Hemodialise",
            "Centro Cirurgico",
            "Consultorio Particular",
            "U.T.I",
            "Lavanderia",
        ]  # "Colaborador"
    }
    
    # Limpar tabela existente
    db(db.tipo_usuario_setor.id > 0).delete()
    
    # Para cada tipo de usuário
    for tipo_id_str, setores_nomes in setores_hardcoded.items():
        tipo_id = int(tipo_id_str)
        # Para cada setor permitido
        for setor_nome in setores_nomes:
            # Buscar o ID do setor pelo nome
            setor = db(db.setor.name == setor_nome).select().first()
            if setor:
                # Inserir na tabela de relacionamento
                db.tipo_usuario_setor.insert(tipo_id=tipo_id, setor_id=setor.id)
    
    # Criar a configuração para uso no JavaScript
    setor_names = {}
    for tipo in db(db.user_type).select():
        setores_do_tipo = db(db.tipo_usuario_setor.tipo_id == tipo.id).select(
            left=db.setor.on(db.tipo_usuario_setor.setor_id == db.setor.id)
        )
        setor_names[str(tipo.id)] = [s.setor.name for s in setores_do_tipo]
    
    # Atualizar ou criar a configuração
    config_setores = db(db.configuracoes.nome == 'setores_por_tipo_colaborador').select().first()
    if config_setores:
        config_setores.update_record(valor=json.dumps(setor_names))
    else:
        db.configuracoes.insert(
            nome='setores_por_tipo_colaborador',
            valor=json.dumps(setor_names),
            descricao='Mapeamento de tipos de usuário para seus setores permitidos',
            tipo='json'
        )
    
    db.commit()
    return "Migração concluída com sucesso!"


@auth.requires_membership('Administrador')
def gerenciar_setores():
    """Permite a configuração dos setores de forma personalizada"""
    # Busca todos os setores ordenados pelo nome
    setores = db(db.setor).select(orderby=db.setor.name)
    
    return dict(setores=setores)

@auth.requires_membership('Administrador')
def adicionar_setor():
    """Adiciona um novo setor"""
    name = request.vars.name
    
    if not name:
        session.flash = "Nome do setor é obrigatório!"
        redirect(URL('gerenciar_setores'))
    
    try:
        db.setor.insert(name=name)
        db.commit()
        session.flash = "Setor adicionado com sucesso!"
    except Exception as e:
        db.rollback()
        session.flash = f"Erro ao adicionar setor: {str(e)}"
    
    redirect(URL('gerenciar_setores'))

@auth.requires_membership('Administrador')
def atualizar_setor():
    """Atualiza um setor existente"""
    setor_id = request.vars.id
    name = request.vars.name
    
    if not setor_id or not name:
        session.flash = "ID e nome do setor são obrigatórios!"
        redirect(URL('gerenciar_setores'))
    
    try:
        setor = db.setor(setor_id)
        if not setor:
            session.flash = "Setor não encontrado!"
            redirect(URL('gerenciar_setores'))
        
        setor.update_record(name=name)
        db.commit()
        session.flash = "Setor atualizado com sucesso!"
    except Exception as e:
        db.rollback()
        session.flash = f"Erro ao atualizar setor: {str(e)}"
    
    redirect(URL('gerenciar_setores'))

@auth.requires_membership('Administrador')
def excluir_setor():
    """Exclui um setor existente"""
    setor_id = request.args(0)
    
    if not setor_id:
        session.flash = "ID do setor é obrigatório!"
        redirect(URL('gerenciar_setores'))
    
    try:
        # Verificar se o setor está sendo usado por algum usuário
        usuarios_com_setor = db(db.auth_user.setor_id == setor_id).count()
        
        if usuarios_com_setor > 0:
            session.flash = f"Não é possível excluir este setor! Existem {usuarios_com_setor} usuários vinculados a ele."
            redirect(URL('gerenciar_setores'))
        
        # Se não estiver em uso, excluir o setor
        db(db.setor.id == setor_id).delete()
        db.commit()
        session.flash = "Setor excluído com sucesso!"
    except Exception as e:
        db.rollback()
        session.flash = f"Erro ao excluir setor: {str(e)}"
    
    redirect(URL('gerenciar_setores'))