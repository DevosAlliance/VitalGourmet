# controllers/admin.py
# Adicione estas funções ao seu admin.py existente

def index():
    """
    Página principal para incorporação de usuários (user impersonation)
    Permite que desenvolvedores assumam temporariamente o papel de outros usuários
    """
    # Verifica se é ambiente de desenvolvimento
    if not request.is_local:
        session.flash = 'Recurso disponível apenas em ambiente de desenvolvimento'
        redirect(URL('default', 'index'))
    
    # Obtém todos os tipos de usuário
    tipos_usuario = db(db.user_type.id > 0).select()
    
    # Obtém todos os setores
    setores = db(db.setor.id > 0).select()
    
    # Obtém usuários para serem incorporados 
    # Limitando para não pegar muitos registros
    usuarios = db(db.auth_user.id > 0).select(
        db.auth_user.id, 
        db.auth_user.first_name, 
        db.auth_user.last_name,
        db.auth_user.user_type,
        db.auth_user.setor_id,
        limitby=(0, 50),
        orderby=db.auth_user.first_name
    )
    
    # Se estiver incorporando um usuário, obtém os detalhes
    usuario_incorporado = None
    if session.impersonating_user_id:
        usuario_incorporado = db.auth_user(session.impersonating_user_id)
    
    return dict(
        tipos_usuario=tipos_usuario,
        setores=setores,
        usuarios=usuarios,
        usuario_incorporado=usuario_incorporado
    )

def iniciar():
    """Inicia a incorporação de um usuário"""
    try:
        # Verifica se é ambiente de desenvolvimento
        if not request.is_local:
            return response.json({'success': False, 'message': 'Recurso disponível apenas em ambiente de desenvolvimento'})
        
        usuario_id = request.vars.usuario_id
        
        if not usuario_id:
            return response.json({'success': False, 'message': 'ID de usuário não fornecido'})
        
        # Salva os dados originais do usuário atual na sessão
        if not session.original_user_id:
            session.original_user_id = auth.user.id if auth.user else None
            session.original_user_type = auth.user.user_type if auth.user else None
            session.original_setor_id = auth.user.setor_id if auth.user else None
        
        # Obtém dados do usuário a ser incorporado
        usuario = db.auth_user(usuario_id)
        if not usuario:
            return response.json({'success': False, 'message': 'Usuário não encontrado'})
        
        # Salva o ID do usuário incorporado na sessão
        session.impersonating_user_id = usuario.id
        
        # Simula os dados do usuário (sem realmente fazer login)
        # Os dados originais foram salvos e podem ser restaurados
        session.impersonation_active = True
        
        # Retorna sucesso
        return response.json({
            'success': True, 
            'message': f'Agora você está vendo o sistema como {usuario.first_name} {usuario.last_name}',
            'usuario': {
                'id': usuario.id,
                'nome': f'{usuario.first_name} {usuario.last_name}',
                'tipo_id': usuario.user_type,
                'tipo_nome': db.user_type[usuario.user_type].name if usuario.user_type else 'Não definido',
                'setor_id': usuario.setor_id,
                'setor_nome': db.setor[usuario.setor_id].name if usuario.setor_id else 'Não definido'
            }
        })
    except Exception as e:
        import traceback
        print(f"ERRO na função iniciar(): {str(e)}")
        print(traceback.format_exc())
        return response.json({'success': False, 'message': f'Erro interno: {str(e)}'})

def alterar_tipo():
    """Altera temporariamente o tipo do usuário incorporado"""
    # Verifica se é ambiente de desenvolvimento
    if not request.is_local:
        return response.json({'success': False, 'message': 'Recurso disponível apenas em ambiente de desenvolvimento'})
    
    # Verifica se está incorporando um usuário
    if not session.impersonating_user_id:
        return response.json({'success': False, 'message': 'Nenhum usuário está sendo incorporado'})
    
    tipo_id = request.vars.tipo_id
    if not tipo_id:
        return response.json({'success': False, 'message': 'ID do tipo de usuário não fornecido'})
    
    # Obtém o tipo de usuário
    tipo = db.user_type(tipo_id)
    if not tipo:
        return response.json({'success': False, 'message': 'Tipo de usuário não encontrado'})
    
    # Salva o tipo temporário
    session.impersonation_user_type = tipo.id
    
    # Retorna sucesso
    return response.json({
        'success': True, 
        'message': f'Tipo de usuário alterado para {tipo.name}',
        'tipo': {
            'id': tipo.id,
            'nome': tipo.name
        }
    })

def alterar_setor():
    """Altera temporariamente o setor do usuário incorporado"""
    # Verifica se é ambiente de desenvolvimento
    if not request.is_local:
        return response.json({'success': False, 'message': 'Recurso disponível apenas em ambiente de desenvolvimento'})
    
    # Verifica se está incorporando um usuário
    if not session.impersonating_user_id:
        return response.json({'success': False, 'message': 'Nenhum usuário está sendo incorporado'})
    
    setor_id = request.vars.setor_id
    if not setor_id:
        return response.json({'success': False, 'message': 'ID do setor não fornecido'})
    
    # Obtém o setor
    setor = db.setor(setor_id)
    if not setor:
        return response.json({'success': False, 'message': 'Setor não encontrado'})
    
    # Salva o setor temporário
    session.impersonation_setor_id = setor.id
    
    # Retorna sucesso
    return response.json({
        'success': True, 
        'message': f'Setor alterado para {setor.name}',
        'setor': {
            'id': setor.id,
            'nome': setor.name
        }
    })

def finalizar():
    """Finaliza a incorporação e restaura os dados originais"""
    # Limpa as variáveis de sessão relacionadas à incorporação
    session.impersonating_user_id = None
    session.original_user_id = None
    session.original_user_type = None
    session.original_setor_id = None
    session.impersonation_user_type = None
    session.impersonation_setor_id = None
    session.impersonation_active = False
    
    # Redireciona para a página inicial
    redirect(URL('default', 'index'))


@auth.requires(lambda: any(auth.has_membership(role) for role in ['Administrador', 'Gestor']))
def gerenciar_pedidos():
    """
    Tela administrativa para gerenciar todos os pedidos (sem limitação de horário)
    """
    # Buscar tipos de usuário para o filtro
    tipos_usuario = db(db.user_type).select(db.user_type.id, db.user_type.name, orderby=db.user_type.name)
    
    # Buscar setores para o filtro
    setores = db(db.setor).select(db.setor.id, db.setor.name, orderby=db.setor.name)
    
    return dict(
        tipos_usuario=tipos_usuario,
        setores=setores
    )

def api_admin_listar_pedidos():
    """
    API para listar pedidos com filtros (AJAX)
    """
    try:
        # Parâmetros de filtro
        filtro_nome = request.vars.nome or ""
        filtro_tipo_usuario = request.vars.tipo_usuario or ""
        filtro_setor = request.vars.setor or ""
        
        # Query base: todos os pedidos não finalizados
        query = (~db.solicitacao_refeicao.status.belongs(['Finalizado', 'Pago']))
        
        # Aplicar filtros
        if filtro_nome:
            query &= db.auth_user.first_name.contains(filtro_nome)
            
        if filtro_tipo_usuario:
            query &= (db.auth_user.user_type == int(filtro_tipo_usuario))
            
        if filtro_setor:
            query &= (db.auth_user.setor_id == int(filtro_setor))
        
        # Buscar pedidos
        pedidos = db(query).select(
            db.solicitacao_refeicao.ALL,
            db.cardapio.foto_do_prato,
            db.cardapio.nome,
            db.cardapio.tipo,
            db.auth_user.first_name,
            db.auth_user.room,
            db.auth_user.observations,
            db.auth_user.user_type,
            db.setor.name,
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ],
            orderby=~db.solicitacao_refeicao.data_solicitacao
        )
        
        # Formatar pedidos para JSON
        pedidos_json = []
        for pedido in pedidos:
            user_type_name = pedido.auth_user.user_type.name if pedido.auth_user.user_type else "Sem Tipo"
            
            pedidos_json.append({
                'id': pedido.solicitacao_refeicao.id,
                'solicitante': pedido.auth_user.first_name,
                'setor': pedido.setor.name or '-',
                'prato': pedido.cardapio.nome,
                'tipo_prato': pedido.cardapio.tipo or '-',
                'foto': f"data:image/png;base64,{pedido.cardapio.foto_do_prato}" if pedido.cardapio.foto_do_prato else '',
                'quantidade': pedido.solicitacao_refeicao.quantidade_solicitada,
                'preco': float(pedido.solicitacao_refeicao.preco or 0),
                'quarto': pedido.auth_user.room or '',
                'observacoes': pedido.auth_user.observations or '',
                'status': pedido.solicitacao_refeicao.status,
                'data_solicitacao': pedido.solicitacao_refeicao.data_solicitacao.strftime('%d/%m/%Y %H:%M') if pedido.solicitacao_refeicao.data_solicitacao else '',
                'tipo_usuario': user_type_name
            })
        
        return response.json({
            'status': 'success', 
            'pedidos': pedidos_json,
            'total': len(pedidos_json)
        })
        
    except Exception as e:
        import traceback
        error_message = f"Erro ao processar a API: {str(e)}\n{traceback.format_exc()}"
        print(error_message)
        return response.json({'status': 'error', 'message': error_message})