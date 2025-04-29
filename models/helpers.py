# models/helpers.py
def is_from_sector(sector_name):
    if not auth.user or not auth.user.setor_id:
        return False
    setor = db.setor[auth.user.setor_id]
    return setor and setor.name == sector_name