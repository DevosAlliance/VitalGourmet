# controllers/admin.py

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
        filtro_data_inicio = request.vars.data_inicio or ""
        filtro_data_fim = request.vars.data_fim or ""
        filtro_ordenacao = request.vars.ordenacao or "data_desc"  # Novo parâmetro
        
        # Query base: todos os pedidos não finalizados
        query = (~db.solicitacao_refeicao.status.belongs(['Pago']))
        
        # Aplicar filtros
        if filtro_nome:
            query &= db.auth_user.first_name.contains(filtro_nome)
            
        if filtro_tipo_usuario:
            query &= (db.auth_user.user_type == int(filtro_tipo_usuario))
            
        if filtro_setor:
            query &= (db.auth_user.setor_id == int(filtro_setor))
        
        # Filtro por data
        if filtro_data_inicio:
            try:
                from datetime import datetime
                data_inicio = datetime.strptime(filtro_data_inicio, '%Y-%m-%d').date()
                query &= (db.solicitacao_refeicao.data_solicitacao >= data_inicio)
            except ValueError:
                pass  # Ignora se a data estiver em formato inválido
                
        if filtro_data_fim:
            try:
                from datetime import datetime, timedelta
                data_fim = datetime.strptime(filtro_data_fim, '%Y-%m-%d').date()
                # Inclui o dia inteiro (até 23:59:59)
                data_fim_completa = datetime.combine(data_fim, datetime.max.time())
                query &= (db.solicitacao_refeicao.data_solicitacao <= data_fim_completa)
            except ValueError:
                pass  # Ignora se a data estiver em formato inválido
        
        # Definir ordenação baseada no parâmetro
        if filtro_ordenacao == "data_asc":
            orderby = db.solicitacao_refeicao.data_solicitacao
        elif filtro_ordenacao == "data_desc":
            orderby = ~db.solicitacao_refeicao.data_solicitacao
        elif filtro_ordenacao == "preco_asc":
            orderby = db.solicitacao_refeicao.preco
        elif filtro_ordenacao == "preco_desc":
            orderby = ~db.solicitacao_refeicao.preco
        else:
            orderby = ~db.solicitacao_refeicao.data_solicitacao  # Padrão: data decrescente
        
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
            orderby=orderby
        )
        
        # Formatar pedidos para JSON
        pedidos_json = []
        for pedido in pedidos:
            user_type_name = pedido.auth_user.user_type.name if pedido.auth_user.user_type else "Sem Tipo"
            
            pedidos_json.append({
                'id': pedido.solicitacao_refeicao.id,
                'solicitante_id': pedido.solicitacao_refeicao.solicitante_id,
                'solicitante': pedido.auth_user.first_name,
                'setor': pedido.setor.name or '-',
                'prato': pedido.cardapio.nome,
                'descricao': pedido.solicitacao_refeicao.descricao or '-',
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
    
     

@auth.requires(lambda: any(auth.has_membership(role) for role in ['Administrador', 'Gestor']))
def ajustar_preco_pedido():
    """
    Ajusta o preço de um pedido - CORRIGIDO para lidar com tipos Decimal/Float
    """
    try:
        pedido_id = request.post_vars.get('pedido_id')
        novo_preco = request.post_vars.get('novo_preco')
        
        # Validações básicas
        if not pedido_id:
            raise ValueError("ID do pedido não fornecido.")
        
        if not novo_preco:
            raise ValueError("Novo preço não fornecido.")
        
        try:
            novo_preco = float(novo_preco)
        except (ValueError, TypeError):
            raise ValueError("Preço inválido. Deve ser um número.")
        
        if novo_preco < 0:
            raise ValueError("O preço não pode ser negativo.")

        if novo_preco > 1000:
            raise ValueError("Preço muito alto. Valor máximo permitido: R$ 1.000,00")

        # 1. CONSULTAR o pedido atual
        pedido = db(db.solicitacao_refeicao.id == pedido_id).select().first()
        if not pedido:
            raise ValueError("Pedido não encontrado.")

        if pedido.status in ['Entregue', 'Cancelado']:
            raise ValueError("Não é possível ajustar o preço de pedidos entregues ou cancelados.")

        # 2. CONVERTER valores para float (evita erro de tipo Decimal)
        preco_antigo = float(pedido.preco or 0)
        solicitante_id = pedido.solicitante_id
        diferenca = novo_preco - preco_antigo

        # Se não há diferença significativa, não fazer nada
        if abs(diferenca) < 0.01:
            return response.json({
                'status': 'success', 
                'message': 'Nenhuma alteração necessária - preços são equivalentes.'
            })

        # 3. CONSULTAR e ajustar saldo do usuário
        saldo_atual = db(db.user_balance.user_id == solicitante_id).select().first()
        
        if not saldo_atual:
            # Criar novo registro se não existir
            novo_saldo = max(0.0, diferenca)
            db.user_balance.insert(
                user_id=solicitante_id,
                saldo_devedor=novo_saldo
            )
        else:
            # CONVERTER saldo atual para float antes da soma
            saldo_atual_float = float(saldo_atual.saldo_devedor or 0)
            novo_saldo_devedor = saldo_atual_float + diferenca
            novo_saldo_devedor = max(0.0, novo_saldo_devedor)  # Nunca negativo
            
            saldo_atual.update_record(saldo_devedor=novo_saldo_devedor)

        # 4. ATUALIZAR o preço do pedido
        pedido.update_record(preco=novo_preco)

        # 5. CONFIRMAR mudanças
        db.commit()

        # 6. PREPARAR resposta
        if diferenca > 0:
            tipo_alteracao = "aumentado"
            impacto_saldo = "acrescido"
        else:
            tipo_alteracao = "reduzido"
            impacto_saldo = "reduzido"
            diferenca = abs(diferenca)

        return response.json({
            'status': 'success',
            'message': f'Preço {tipo_alteracao} com sucesso! Saldo do cliente foi {impacto_saldo} em R$ {diferenca:.2f}',
            'preco_antigo': preco_antigo,
            'novo_preco': novo_preco,
            'diferenca': diferenca
        })

    except Exception as e:
        db.rollback()
        return response.json({
            'status': 'error',
            'message': str(e)
        })


# VERSÃO ALTERNATIVA usando Decimal (se preferir manter tipos decimais)
from decimal import Decimal

@auth.requires(lambda: any(auth.has_membership(role) for role in ['Administrador', 'Gestor']))
def ajustar_preco_pedido_decimal():
    """
    Versão usando Decimal para maior precisão em cálculos financeiros
    """
    try:
        pedido_id = request.post_vars.get('pedido_id')
        novo_preco = request.post_vars.get('novo_preco')
        
        if not pedido_id or not novo_preco:
            raise ValueError("Dados obrigatórios não fornecidos.")
        
        try:
            # Converter para Decimal desde o início
            novo_preco = Decimal(str(novo_preco))
        except:
            raise ValueError("Preço inválido.")
        
        if novo_preco < 0:
            raise ValueError("O preço não pode ser negativo.")

        # Consultar pedido
        pedido = db(db.solicitacao_refeicao.id == pedido_id).select().first()
        if not pedido:
            raise ValueError("Pedido não encontrado.")

        if pedido.status in ['Entregue', 'Cancelado']:
            raise ValueError("Não é possível ajustar o preço de pedidos entregues ou cancelados.")

        # Converter preço antigo para Decimal
        preco_antigo = Decimal(str(pedido.preco or 0))
        diferenca = novo_preco - preco_antigo

        if abs(diferenca) < Decimal('0.01'):
            return response.json({
                'status': 'success', 
                'message': 'Preços são equivalentes.'
            })

        # Ajustar saldo
        saldo_atual = db(db.user_balance.user_id == pedido.solicitante_id).select().first()
        
        if not saldo_atual:
            novo_saldo = max(Decimal('0'), diferenca)
            db.user_balance.insert(
                user_id=pedido.solicitante_id,
                saldo_devedor=novo_saldo
            )
        else:
            # Manter como Decimal
            saldo_atual_decimal = Decimal(str(saldo_atual.saldo_devedor or 0))
            novo_saldo_devedor = saldo_atual_decimal + diferenca
            novo_saldo_devedor = max(Decimal('0'), novo_saldo_devedor)
            
            saldo_atual.update_record(saldo_devedor=novo_saldo_devedor)

        # Atualizar preço
        pedido.update_record(preco=novo_preco)
        db.commit()

        # Resposta
        tipo = "aumentado" if diferenca > 0 else "reduzido"
        return response.json({
            'status': 'success',
            'message': f'Preço {tipo} com sucesso! Diferença: R$ {abs(diferenca):.2f}'
        })

    except Exception as e:
        db.rollback()
        return response.json({
            'status': 'error',
            'message': str(e)
        })


# VERSÃO MAIS SIMPLES E ROBUSTA (RECOMENDADA)
@auth.requires(lambda: any(auth.has_membership(role) for role in ['Administrador', 'Gestor']))
def ajustar_preco_pedido_simples():
    """
    Versão mais simples e robusta - converte tudo para float
    """
    try:
        pedido_id = request.post_vars.get('pedido_id')
        novo_preco_str = request.post_vars.get('novo_preco')
        
        # Validações
        if not pedido_id or not novo_preco_str:
            raise ValueError("Dados obrigatórios não fornecidos.")
        
        novo_preco = float(novo_preco_str)
        if novo_preco < 0:
            raise ValueError("Preço inválido.")

        # Buscar pedido
        pedido = db(db.solicitacao_refeicao.id == pedido_id).select().first()
        if not pedido:
            raise ValueError("Pedido não encontrado.")

        # Calcular diferença (convertendo tudo para float)
        preco_antigo = float(pedido.preco or 0)
        diferenca = novo_preco - preco_antigo

        if abs(diferenca) < 0.01:
            return response.json({'status': 'success', 'message': 'Preços iguais.'})

        # Atualizar saldo (convertendo para float)
        saldo = db(db.user_balance.user_id == pedido.solicitante_id).select().first()
        if saldo:
            saldo_atual = float(saldo.saldo_devedor or 0)
            novo_saldo = max(0.0, saldo_atual + diferenca)
            saldo.update_record(saldo_devedor=novo_saldo)
        else:
            db.user_balance.insert(
                user_id=pedido.solicitante_id,
                saldo_devedor=max(0.0, diferenca)
            )

        # Atualizar preço
        pedido.update_record(preco=novo_preco)
        db.commit()

        return response.json({
            'status': 'success',
            'message': f'Preço ajustado! Diferença: R$ {abs(diferenca):.2f}'
        })

    except Exception as e:
        db.rollback()
        return response.json({'status': 'error', 'message': str(e)})
    


    


# --------------------------------------------------------------------

def verificar_inconsistencias_saldo():
    """
    Função auxiliar para identificar inconsistências entre solicitações não pagas
    e o saldo registrado na user_balance, sem fazer correções.
    
    Returns:
        dict: Relatório das inconsistências encontradas
    """
    try:
        # Calcular saldo real baseado nas solicitações não pagas
        query = """
        SELECT 
            solicitante_id,
            SUM(preco) as saldo_real
        FROM solicitacao_refeicao 
        WHERE foi_pago = 0 
        GROUP BY solicitante_id
        """
        
        saldos_reais = db.executesql(query, as_dict=True)
        saldos_reais_dict = {r['solicitante_id']: r['saldo_real'] for r in saldos_reais}
        
        # Buscar todos os saldos registrados
        balances = db(db.user_balance).select()
        
        inconsistencias = []
        
        # Verificar inconsistências
        for balance in balances:
            saldo_registrado = balance.saldo_devedor
            saldo_real = saldos_reais_dict.get(balance.user_id, 0)
            
            if abs(saldo_registrado - saldo_real) > 0.01:  # Tolerância para diferenças de centavos
                inconsistencias.append({
                    'user_id': balance.user_id,
                    'saldo_registrado': float(saldo_registrado),
                    'saldo_real': float(saldo_real),
                    'diferenca': float(saldo_real - saldo_registrado)
                })
        
        # Verificar usuários com dívidas que não estão na user_balance
        for user_id, saldo_real in saldos_reais_dict.items():
            balance_existente = db(db.user_balance.user_id == user_id).select().first()
            if not balance_existente and saldo_real > 0:
                inconsistencias.append({
                    'user_id': user_id,
                    'saldo_registrado': 0.0,
                    'saldo_real': float(saldo_real),
                    'diferenca': float(saldo_real),
                    'status': 'usuario_sem_balance'
                })
        
        return {
            'total_inconsistencias': len(inconsistencias),
            'inconsistencias': inconsistencias,
            'requer_correcao': len(inconsistencias) > 0
        }
        
    except Exception as e:
        return {
            'erro': str(e),
            'mensagem': 'Erro ao verificar inconsistências'
        }


def api_corrigir_saldo_devedor():
    """
    API para corrigir saldos devedores de todos os usuários.
    Acesso restrito a administradores.
    """
    # Verificar permissões
    if not auth.has_membership('Administrador'):
        return dict(
            erro=True,
            mensagem="Acesso negado. Apenas administradores podem executar esta operação."
        )
    
    try:
        # Executar correção com relatório completo
        resultado = executar_correcao_saldo_com_relatorio()
        
        return dict(
            erro=False,
            dados=resultado,
            mensagem=resultado.get('mensagem', 'Operação concluída')
        )
        
    except Exception as e:
        return dict(
            erro=True,
            mensagem=f"Erro inesperado: {str(e)}"
        )


def api_verificar_inconsistencias():
    """
    API para apenas verificar inconsistências sem corrigir.
    """
    if not auth.has_membership('Administrador'):
        return dict(
            erro=True,
            mensagem="Acesso negado."
        )
    
    try:
        resultado = verificar_inconsistencias_saldo()
        
        return dict(
            erro=False,
            dados=resultado,
            mensagem="Verificação concluída"
        )
        
    except Exception as e:
        return dict(
            erro=True,
            mensagem=f"Erro ao verificar: {str(e)}"
        )


def correcao_saldo():
    """
    Página administrativa para correção manual de saldos.
    """
    if not auth.has_membership('Administrador'):
        redirect(URL('default', 'index'))
    
    # Formulário para confirmar a operação
    form = FORM(
        DIV(
            H4("Correção de Saldo Devedor"),
            P("Esta operação irá recalcular os saldos devedores de todos os usuários baseado nas solicitações não pagas."),
            P("Recomenda-se fazer um backup antes de executar.", _class="text-warning"),
            BR(),
            INPUT(_type="submit", _value="Verificar Inconsistências", _name="verificar", _class="btn btn-info"),
            " ",
            INPUT(_type="submit", _value="Executar Correção", _name="corrigir", _class="btn btn-warning"),
            _class="card-body"
        ),
        _class="card"
    )
    
    resultado = None
    
    if form.process().accepted:
        try:
            if request.vars.verificar:
                # Apenas verificar
                resultado = verificar_inconsistencias_saldo()
                resultado['tipo'] = 'verificacao'
                
            elif request.vars.corrigir:
                # Executar correção
                resultado = executar_correcao_saldo_com_relatorio()
                resultado['tipo'] = 'correcao'
                
        except Exception as e:
            response.flash = f"Erro: {str(e)}"
    
    return dict(form=form, resultado=resultado)

def corrigir_saldo_devedor_usuarios():
    """
    Função que varre todas as solicitações não pagas e corrige o saldo devedor
    dos usuários na tabela user_balance.
    
    Returns:
        dict: Relatório da operação com usuários atualizados e valores
    """
    try:
        # Buscar todas as solicitações não pagas agrupadas por usuário
        query = """
        SELECT 
            solicitante_id,
            SUM(preco) as total_devedor
        FROM solicitacao_refeicao 
        WHERE foi_pago = 0 
        GROUP BY solicitante_id
        """
        
        # Executar a query usando DAL
        solicitacoes_nao_pagas = db.executesql(query, as_dict=True)
        
        usuarios_atualizados = []
        total_usuarios = 0
        valor_total_ajustado = 0
        
        # Para cada usuário com saldo devedor
        for registro in solicitacoes_nao_pagas:
            user_id = registro['solicitante_id']
            saldo_correto = registro['total_devedor']
            
            # Verificar se já existe registro na user_balance
            balance_existente = db(db.user_balance.user_id == user_id).select().first()
            
            if balance_existente:
                # Atualizar registro existente
                saldo_anterior = balance_existente.saldo_devedor
                db(db.user_balance.user_id == user_id).update(
                    saldo_devedor=saldo_correto,
                    updated_at=request.now
                )
                
                usuarios_atualizados.append({
                    'user_id': user_id,
                    'saldo_anterior': float(saldo_anterior),
                    'saldo_correto': float(saldo_correto),
                    'diferenca': float(saldo_correto - saldo_anterior),
                    'acao': 'atualizado'
                })
            else:
                # Criar novo registro
                db.user_balance.insert(
                    user_id=user_id,
                    saldo_devedor=saldo_correto,
                    updated_at=request.now
                )
                
                usuarios_atualizados.append({
                    'user_id': user_id,
                    'saldo_anterior': 0.0,
                    'saldo_correto': float(saldo_correto),
                    'diferenca': float(saldo_correto),
                    'acao': 'criado'
                })
            
            total_usuarios += 1
            valor_total_ajustado += saldo_correto
        
        # Buscar usuários que não têm mais dívidas (todos os pedidos foram pagos)
        # mas ainda têm saldo devedor na tabela
        usuarios_com_balance = db(db.user_balance.saldo_devedor > 0).select()
        
        for balance in usuarios_com_balance:
            # Verificar se este usuário realmente tem dívidas
            tem_dividas = db((db.solicitacao_refeicao.solicitante_id == balance.user_id) & 
                           (db.solicitacao_refeicao.foi_pago == False)).count()
            
            if tem_dividas == 0:
                # Zerar saldo devedor
                saldo_anterior = balance.saldo_devedor
                db(db.user_balance.user_id == balance.user_id).update(
                    saldo_devedor=0,
                    updated_at=request.now
                )
                
                usuarios_atualizados.append({
                    'user_id': balance.user_id,
                    'saldo_anterior': float(saldo_anterior),
                    'saldo_correto': 0.0,
                    'diferenca': float(-saldo_anterior),
                    'acao': 'zerado'
                })
                
                total_usuarios += 1
        
        # Commit das alterações
        db.commit()
        
        # Criar log da operação
        db.log_sistema.insert(
            user_id=auth.user.id if auth.user else 1,
            entidade='user_balance',
            acao='edicao',
            registro_id=0,  # Operação em massa
            observacao={
                'tipo': 'correcao_saldo_devedor',
                'usuarios_afetados': total_usuarios,
                'valor_total': float(valor_total_ajustado),
                'detalhes': usuarios_atualizados
            }
        )
        
        return {
            'sucesso': True,
            'total_usuarios_atualizados': total_usuarios,
            'valor_total_ajustado': float(valor_total_ajustado),
            'usuarios_atualizados': usuarios_atualizados,
            'mensagem': f'Saldo devedor corrigido para {total_usuarios} usuários'
        }
        
    except Exception as e:
        # Em caso de erro, fazer rollback
        db.rollback()
        
        # Log do erro
        if auth.user:
            db.log_sistema.insert(
                user_id=auth.user.id,
                entidade='user_balance',
                acao='edicao',
                registro_id=0,
                observacao={
                    'tipo': 'erro_correcao_saldo',
                    'erro': str(e)
                }
            )
        
        return {
            'sucesso': False,
            'erro': str(e),
            'mensagem': 'Erro ao corrigir saldo devedor dos usuários'
        }
    
def executar_correcao_saldo_com_relatorio():
    """
    Função que combina verificação e correção, gerando um relatório completo.
    
    Returns:
        dict: Relatório completo da operação
    """
    # Primeiro verificar inconsistências
    relatorio_inconsistencias = verificar_inconsistencias_saldo()
    
    if not relatorio_inconsistencias.get('requer_correcao', False):
        return {
            'sucesso': True,
            'mensagem': 'Nenhuma inconsistência encontrada. Saldos já estão corretos.',
            'inconsistencias_encontradas': 0,
            'correcoes_realizadas': 0
        }
    
    # Se há inconsistências, executar correção
    resultado_correcao = corrigir_saldo_devedor_usuarios()
    
    return {
        'sucesso': resultado_correcao['sucesso'],
        'inconsistencias_encontradas': relatorio_inconsistencias['total_inconsistencias'],
        'correcoes_realizadas': resultado_correcao.get('total_usuarios_atualizados', 0),
        'valor_total_ajustado': resultado_correcao.get('valor_total_ajustado', 0),
        'detalhes_inconsistencias': relatorio_inconsistencias['inconsistencias'],
        'detalhes_correcoes': resultado_correcao.get('usuarios_atualizados', []),
        'mensagem': resultado_correcao.get('mensagem', '')
    }

def task_correcao_automatica():
    """
    Task para ser executada via scheduler periodicamente (ex: diariamente às 2h da manhã).
    """
    try:
        # Verificar se há inconsistências
        verificacao = verificar_inconsistencias_saldo()
        
        if verificacao.get('requer_correcao', False):
            # Se há inconsistências, corrigir
            resultado = corrigir_saldo_devedor_usuarios()
            
            # Log da operação automática
            db.log_sistema.insert(
                user_id=1,  # Sistema
                entidade='user_balance',
                acao='edicao',
                registro_id=0,
                observacao={
                    'tipo': 'correcao_automatica',
                    'inconsistencias_encontradas': verificacao['total_inconsistencias'],
                    'usuarios_corrigidos': resultado.get('total_usuarios_atualizados', 0),
                    'executado_em': request.now
                }
            )
            
            return f"Correção automática executada: {resultado.get('total_usuarios_atualizados', 0)} usuários atualizados"
        else:
            return "Nenhuma inconsistência encontrada"
            
    except Exception as e:
        # Log do erro
        db.log_sistema.insert(
            user_id=1,
            entidade='user_balance',
            acao='edicao',
            registro_id=0,
            observacao={
                'tipo': 'erro_correcao_automatica',
                'erro': str(e),
                'executado_em': request.now
            }
        )
        raise e