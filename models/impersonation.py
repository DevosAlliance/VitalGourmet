# models/impersonation.py
import os
from gluon import current, URL
from gluon.storage import Storage
from gluon.globals import Request, Session
from gluon.http import redirect

def impersonation_handler():
    """
    Manipula a incorporação de usuários para testes
    Substituindo completamente o usuário logado pelo usuário incorporado
    """
    # Verifica se a incorporação está ativa e se estamos em ambiente de desenvolvimento
    if current.request.is_local and hasattr(current.session, 'impersonation_active') and current.session.impersonation_active:
        # Obtém o usuário incorporado
        if hasattr(current.session, 'impersonating_user_id') and current.session.impersonating_user_id:
            # Backup do usuário original se ainda não tiver sido feito
            if not hasattr(current, '_original_auth_user'):
                current._original_auth_user = current.auth.user
                current._original_has_membership = current.auth.has_membership
            
            # Obtém o usuário completo do banco de dados
            usuario_id = current.session.impersonating_user_id
            usuario_incorporado = current.db.auth_user(usuario_id)
            
            if usuario_incorporado:
                # Sobreposições específicas, se existirem
                if hasattr(current.session, 'impersonation_user_type') and current.session.impersonation_user_type:
                    usuario_incorporado.user_type = current.session.impersonation_user_type
                
                if hasattr(current.session, 'impersonation_setor_id') and current.session.impersonation_setor_id:
                    usuario_incorporado.setor_id = current.session.impersonation_setor_id
                
                # Cria uma cópia completa do usuário
                user_copy = Storage({})
                for key in usuario_incorporado:
                    user_copy[key] = usuario_incorporado[key]
                
                # Marca o usuário como incorporado (para referência)
                user_copy._impersonated = True
                
                # IMPORTANTE: Substitui completamente o usuário atual
                current.auth.user = user_copy
                
                # Limpa quaisquer caches de permissão
                if hasattr(current.auth, 'user_groups'):
                    delattr(current.auth, 'user_groups')
                
                # Obtém os grupos do usuário incorporado
                grupos_incorporado = current.db(
                    (current.db.auth_membership.user_id == usuario_id)
                ).select(current.db.auth_membership.group_id)
                
                grupos_ids = [g.group_id for g in grupos_incorporado]
                
                # Cria uma função de verificação de associação baseada apenas nos grupos do usuário incorporado
                def impersonated_has_membership(role=None, user_id=None, group_id=None):
                    # Se estamos verificando outro usuário que não o incorporado
                    if user_id is not None and user_id != usuario_id:
                        return False
                    
                    # Se estamos verificando um grupo específico
                    if group_id is not None:
                        return group_id in grupos_ids
                    
                    # Se estamos verificando um papel específico
                    if role is not None:
                        grupo = current.db(current.db.auth_group.role == role).select().first()
                        if not grupo:
                            return False
                        return grupo.id in grupos_ids
                    
                    return False
                
                # Substitui o método has_membership
                current.auth.has_membership = impersonated_has_membership
                
                # Para casos onde o código verifica diretamente db.user_type[auth.user.user_type].name
                # Vamos garantir que isso também seja consistente
                if hasattr(current.session, 'impersonation_user_type') and current.session.impersonation_user_type:
                    # Força a atualização do type_name no auth.user
                    tipo = current.db.user_type[current.session.impersonation_user_type]
                    if tipo:
                        # Inject a property into the user object to override the type name checks
                        class UserTypeWrapper:
                            def __init__(self, id, name):
                                self.id = id
                                self.name = name
                                
                            def __getitem__(self, key):
                                if key == 'name':
                                    return self.name
                                return None
                        
                        user_copy._type_wrapper = UserTypeWrapper(tipo.id, tipo.name)
                        
                        # Monkey patch to intercept the db.user_type[auth.user.user_type] access
                        original_getitem = current.db.user_type.__getitem__
                        
                        def patched_getitem(key):
                            if key == user_copy.user_type:
                                return user_copy._type_wrapper
                            return original_getitem(key)
                        
                        current.db.user_type.__getitem__ = patched_getitem

# Registra o manipulador para ser executado antes de cada requisição
current.response.impersonation_handler = impersonation_handler