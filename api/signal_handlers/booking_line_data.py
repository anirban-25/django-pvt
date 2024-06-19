import logging

from api.models import DME_clients, Client_Auto_Augment, Client_Process_Mgr
from api.operations.booking.auto_augment import auto_augment as auto_augment_oper

logger = logging.getLogger(__name__)


def post_delete_handler(instance):
    booking = instance.booking()
    cl_proc = Client_Process_Mgr.objects.filter(fk_booking_id=booking.pk).first()

    if cl_proc:
        # Get client_auto_augment
        dme_client = DME_clients.objects.filter(
            dme_account_num=booking.kf_client_id
        ).first()

        client_auto_augment = Client_Auto_Augment.objects.filter(
            fk_id_dme_client_id=dme_client.pk_id_dme_client,
            de_to_companyName__iexact=booking.deToCompanyName.strip().lower(),
        ).first()

        if not client_auto_augment:
            logger.error(
                f"#602 This Client is not set up for auto augment, bookingID: {booking.pk}"
            )

        auto_augment_oper(booking, client_auto_augment, cl_proc)
