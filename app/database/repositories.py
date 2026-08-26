import json
from sqlalchemy import select, func
from .models import GoogleAccount, Service, AccountService, ScanHistory

def get_accounts(session):
    return session.scalars(select(GoogleAccount).order_by(GoogleAccount.email)).all()

def get_account(session, account_id):
    return session.get(GoogleAccount, account_id)

def delete_account(session, account_id):
    account = session.get(GoogleAccount, account_id)
    if account:
        session.delete(account)
        session.commit()

def get_or_create_service(session, definition):
    service = session.scalar(select(Service).where(Service.name == definition["name"]))
    if service:
        return service
    service = Service(
        name=definition["name"],
        category=definition.get("category", "Inconnu"),
        subcategory=definition.get("subcategory"),
        logo=definition.get("logo"),
        description=definition.get("description"),
        domains_json=json.dumps(definition.get("domains", [])),
        senders_json=json.dumps(definition.get("senders", [])),
        keywords_json=json.dumps(definition.get("keywords", [])),
    )
    session.add(service)
    session.flush()
    return service

def get_account_services(session, account_id):
    stmt = select(AccountService).where(AccountService.account_id == account_id).join(Service).order_by(AccountService.confidence_score.desc())
    return session.scalars(stmt).all()

def dashboard_counts(session):
    accounts = session.scalar(select(func.count(GoogleAccount.id))) or 0
    services = session.scalar(select(func.count(AccountService.id))) or 0
    migrated = session.scalar(select(func.count(AccountService.id)).where(AccountService.status == "Migré")) or 0
    abandoned = session.scalar(select(func.count(AccountService.id)).where(AccountService.status == "Abandonné")) or 0
    to_check = session.scalar(select(func.count(AccountService.id)).where(AccountService.status == "À vérifier")) or 0
    return accounts, services, migrated, abandoned, to_check
