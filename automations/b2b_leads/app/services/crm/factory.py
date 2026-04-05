import os
from app.services.crm.base import BaseCRM


def get_crm() -> BaseCRM:
    """Возвращает CRM-адаптер в зависимости от настроек."""
    crm_type = os.getenv("CRM_TYPE", "internal").lower()

    if crm_type == "bitrix24" and os.getenv("BITRIX24_WEBHOOK_URL"):
        from app.services.crm.bitrix import BitrixCRM
        return BitrixCRM()

    if crm_type == "amocrm" and os.getenv("AMOCRM_TOKEN"):
        from app.services.crm.amocrm import AmoCRM
        return AmoCRM()

    from app.services.crm.internal import InternalCRM
    return InternalCRM()
