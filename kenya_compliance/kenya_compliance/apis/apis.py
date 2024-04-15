import asyncio
import json
from functools import partial

import aiohttp
import frappe
from frappe.integrations.utils import create_request_log

from kenya_compliance.kenya_compliance.utils import update_last_request_date

from ..doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME
from ..handlers import handle_errors
from ..logger import etims_logger
from ..utils import (
    build_datetime_from_string,
    build_headers,
    get_route_path,
    get_server_url,
    make_post_request,
    update_last_request_date,
)
from .api_builder import EndpointsBuilder
from .remote_response_status_handlers import (
    customer_search_on_success,
    item_registration_on_success,
    on_error,
    customer_insurance_details_submission_on_success,
    customer_branch_details_submission_on_success,
    employee_user_details_submission_on_success,
    inventory_submission_on_success,
)

endpoints_builder = EndpointsBuilder()


@frappe.whitelist()
def bulk_submit_sales_invoices(docs_list: str) -> None:
    from ..overrides.server.sales_invoice import on_submit

    data = json.loads(docs_list)
    all_sales_invoices = frappe.db.get_all("Sales Invoice", ["*"])

    for record in data:
        for invoice in all_sales_invoices:
            if record == invoice.name:
                doc = frappe.get_doc("Sales Invoice", record, for_update=False)
                on_submit(doc, method=None)


@frappe.whitelist()
def bulk_pos_sales_invoices(docs_list: str) -> None:
    from ..overrides.server.pos_invoice import on_submit

    data = json.loads(docs_list)
    all_pos_invoices = frappe.db.get_all("POS Invoice", ["*"])

    for record in data:
        for invoice in all_pos_invoices:
            if record == invoice.name:
                doc = frappe.get_doc("POS Invoice", record, for_update=False)
                on_submit(doc, method=None)


@frappe.whitelist(allow_guest=True)
def perform_customer_search(request_data: str) -> None:
    """Search customer details in the eTims Server

    Args:
        request_data (str): Data received from the client
    """
    data = json.loads(request_data)

    company_name = data["company_name"]

    headers = build_headers(company_name)
    server_url = get_server_url(company_name)
    route_path, last_request_date = get_route_path("CustSearchReq")

    if headers and server_url and route_path:
        url = f"{server_url}{route_path}"
        payload = {"custmTin": data["tax_id"]}

        endpoints_builder.headers = headers
        endpoints_builder.url = url
        endpoints_builder.payload = payload
        endpoints_builder.success_callback = partial(
            customer_search_on_success, document_name=data["name"]
        )
        endpoints_builder.error_callback = on_error

        frappe.enqueue(
            endpoints_builder.make_remote_call,
            is_async=True,
            queue="default",
            timeout=300,
            doctype="Customer",
            document_name=data["name"],
        )


@frappe.whitelist()
def perform_item_registration(request_data: str) -> dict | None:
    data = json.loads(request_data)

    company_name = data.pop("company_name")

    headers = build_headers(company_name)
    server_url = get_server_url(company_name)
    route_path, last_request_date = get_route_path("ItemSaveReq")

    if headers and server_url and route_path:
        url = f"{server_url}{route_path}"

        endpoints_builder.headers = headers
        endpoints_builder.url = url
        endpoints_builder.payload = data
        endpoints_builder.success_callback = partial(
            item_registration_on_success, document_name=data["name"]
        )
        endpoints_builder.error_callback = on_error

        frappe.enqueue(
            endpoints_builder.make_remote_call,
            is_async=True,
            queue="default",
            timeout=300,
            doctype="Item",
            document_name=data["name"],
        )


@frappe.whitelist()
def send_insurance_details(request_data: str) -> None:
    data = json.loads(request_data)

    company_name = data["company_name"]

    headers = build_headers(company_name)
    server_url = get_server_url(company_name)
    route_path, last_request_date = get_route_path("BhfInsuranceSaveReq")

    if headers and server_url and route_path:
        url = f"{server_url}{route_path}"
        payload = {
            "isrccCd": data["insurance_code"],
            "isrccNm": data["insurance_name"],
            "isrcRt": data["premium_rate"],
            "useYn": "Y",
            "regrNm": data["registration_id"],
            "regrId": data["registration_id"],
            "modrNm": data["modifier_id"],
            "modrId": data["modifier_id"],
        }

        endpoints_builder.headers = headers
        endpoints_builder.url = url
        endpoints_builder.payload = payload
        endpoints_builder.success_callback = partial(
            customer_insurance_details_submission_on_success, document_name=data["name"]
        )
        endpoints_builder.error_callback = on_error

        frappe.enqueue(
            endpoints_builder.make_remote_call,
            is_async=True,
            queue="default",
            timeout=300,
            doctype="Customer",
            document_name=data["name"],
        )


@frappe.whitelist()
def send_branch_customer_details(request_data: str) -> None:
    data = json.loads(request_data)

    company_name = data["company_name"]

    headers = build_headers(company_name)
    server_url = get_server_url(company_name)
    route_path, last_request_date = get_route_path("BhfCustSaveReq")

    if headers and server_url and route_path:
        url = f"{server_url}{route_path}"
        payload = {
            "custNo": data["name"][:14],
            "custTin": data["customer_pin"],
            "custNm": data["customer_name"],
            "adrs": None,
            "telNo": None,
            "email": None,
            "faxNo": None,
            "useYn": "Y",
            "remark": None,
            "regrNm": data["registration_id"],
            "regrId": data["registration_id"],
            "modrNm": data["modifier_id"],
            "modrId": data["modifier_id"],
        }

        endpoints_builder.headers = headers
        endpoints_builder.url = url
        endpoints_builder.payload = payload
        endpoints_builder.success_callback = partial(
            customer_branch_details_submission_on_success, document_name=data["name"]
        )
        endpoints_builder.error_callback = on_error

        frappe.enqueue(
            endpoints_builder.make_remote_call,
            is_async=True,
            queue="default",
            timeout=300,
            doctype="Customer",
            document_name=data["name"],
        )


@frappe.whitelist()
def save_branch_user_details(request_data: str) -> None:
    data = json.loads(request_data)
    company_name = data["company_name"]
    headers = build_headers(company_name)
    server_url = get_server_url(company_name)
    route_path, last_request_date = get_route_path("BhfUserSaveReq")

    if headers and server_url and route_path:
        url = f"{server_url}{route_path}"

        payload = {
            "userId": data["user_id"],
            "userNm": data["user_id"],
            "pwd": "password",
            "adrs": None,
            "cntc": None,
            "authCd": None,
            "remark": None,
            "useYn": "Y",
            "regrNm": data["registration_id"],
            "regrId": data["registration_id"],
            "modrNm": data["modifier_id"],
            "modrId": data["modifier_id"],
        }

        endpoints_builder.headers = headers
        endpoints_builder.url = url
        endpoints_builder.payload = payload
        endpoints_builder.success_callback = partial(
            employee_user_details_submission_on_success, document_name=data["name"]
        )
        endpoints_builder.error_callback = on_error

        frappe.enqueue(
            endpoints_builder.make_remote_call,
            is_async=True,
            queue="default",
            timeout=300,
            job_name=f"{data['name']}_send_branch_user_information",
            doctype="Employee",
            document_name=data["name"],
        )


@frappe.whitelist()
def perform_item_search(request_data: str) -> None:
    data = json.loads(request_data)

    company_name = data["company_name"]
    headers = build_headers(company_name)
    server_url = get_server_url(company_name)
    route_path, last_request_date = get_route_path("ItemSearchReq")

    if headers and server_url and route_path:
        url = f"{server_url}{route_path}"

        request_date = last_request_date.strftime("%Y%m%d%H%M%S")
        payload = {"lastReqDt": request_date}

        endpoints_builder.headers = headers
        endpoints_builder.url = url
        endpoints_builder.payload = payload
        endpoints_builder.success_callback = lambda response: frappe.msgprint(
            f"{response}"
        )
        endpoints_builder.error_callback = on_error

        endpoints_builder.make_remote_call(doctype="Item")


@frappe.whitelist()
def perform_import_item_search(request_data: str) -> None:
    data = json.loads(request_data)

    company_name = data["company_name"]
    headers = build_headers(company_name)
    server_url = get_server_url(company_name)
    route_path, last_request_date = get_route_path("ImportItemSearchReq")

    if headers and server_url and route_path:
        request_date = last_request_date.strftime("%Y%m%d%H%M%S")
        url = f"{server_url}{route_path}"
        payload = {"lastReqDt": request_date}

        endpoints_builder.headers = headers
        endpoints_builder.url = url
        endpoints_builder.payload = payload
        endpoints_builder.success_callback = lambda response: frappe.msgprint(
            f"{response}"
        )
        endpoints_builder.error_callback = on_error

        endpoints_builder.make_remote_call(
            doctype="Item",
        )


@frappe.whitelist()
def perform_purchases_search(request_data: str) -> None:
    data = json.loads(request_data)

    company_name = data["company_name"]

    headers = build_headers(company_name)
    server_url = get_server_url(company_name)
    route_path, last_request_date = get_route_path("TrnsPurchaseSalesReq")

    if headers and server_url and route_path:
        request_date = last_request_date.strftime("%Y%m%d%H%M%S")

        url = f"{server_url}{route_path}"
        payload = {"lastReqDt": request_date}

        endpoints_builder.headers = headers
        endpoints_builder.url = url
        endpoints_builder.payload = payload
        endpoints_builder.success_callback = lambda response: frappe.msgprint(
            f"{response}"
        )
        endpoints_builder.error_callback = on_error

        endpoints_builder.make_remote_call(
            doctype="Purchase Invoice",
        )


@frappe.whitelist()
def submit_inventory(request_data: str) -> None:
    data = json.loads(request_data)

    company_name = data["company_name"]

    headers = build_headers(company_name)
    server_url = get_server_url(company_name)
    route_path, last_request_date = get_route_path("StockMasterSaveReq")

    if headers and server_url and route_path:
        url = f"{server_url}{route_path}"

        query = f"""
            SELECT item_code,
                SUM(actual_qty) AS item_count
            FROM tabBin
            WHERE item_code = '{data["name"]}'
            GROUP BY item_code
            ORDER BY item_code DESC;
            """
        results = frappe.db.sql(query, as_dict=True)

        if results:
            payload = {
                "itemCd": data["itemCd"],
                "rsdQty": results[0].item_count,
                "regrId": data["registered_by"],
                "regrNm": data["registered_by"],
                "modrNm": data["registered_by"],
                "modrId": data["registered_by"],
            }

            endpoints_builder.headers = headers
            endpoints_builder.url = url
            endpoints_builder.payload = payload
            endpoints_builder.success_callback = partial(
                inventory_submission_on_success, document_name=data["name"]
            )
            endpoints_builder.error_callback = on_error

            frappe.enqueue(
                endpoints_builder.make_remote_call,
                is_async=True,
                queue="default",
                timeout=300,
                job_name=f"{data['name']}_submit_inventory",
                doctype="Item",
                document_name=data["name"],
            )


@frappe.whitelist()
def perform_item_classification_search(request_data: str) -> None:
    data = json.loads(request_data)

    company_name = data["company_name"]
    headers = build_headers(company_name)

    if headers:
        server_url = get_server_url(company_name)
        route_path, last_request_date = get_route_path("ItemClsSearchReq")
        request_date = last_request_date.strftime("%Y%m%d%H%M%S")

        if server_url and route_path:
            url = f"{server_url}{route_path}"
            payload = {"lastReqDt": request_date}

            try:
                response = asyncio.run(make_post_request(url, payload, headers))

                if response["resultCd"] == "000":
                    frappe.msgprint(f"response: {response}")

                else:
                    handle_errors(
                        response, route_path, document_name=None, doctype="Item"
                    )

            except aiohttp.client_exceptions.ClientConnectorError as error:
                etims_logger.exception(error, exc_info=True)
                frappe.throw(
                    "Connection failed",
                    error,
                    title="Connection Error",
                )

            except asyncio.exceptions.TimeoutError as error:
                etims_logger.exception(error, exc_info=True)
                frappe.throw("Timeout Encountered", error, title="Timeout Error")


@frappe.whitelist()
def search_branch_request(request_data: str) -> None:
    data = json.loads(request_data)

    company_name = data["company_name"]
    headers = build_headers(company_name)

    if headers:
        server_url = get_server_url(company_name)
        route_path, last_request_date = get_route_path("BhfSearchReq")
        request_date = last_request_date.strftime("%Y%m%d%H%M%S")

        if server_url and route_path:
            url = f"{server_url}{route_path}"
            payload = {"lastReqDt": request_date}

            try:
                response = asyncio.run(make_post_request(url, payload, headers))

                if response["resultCd"] == "000":
                    frappe.msgprint(f"response: {response}")

                    update_last_request_date(response["resultDt"], route_path)

                else:
                    frappe.msgprint("Failure")

            except aiohttp.client_exceptions.ClientConnectorError as error:
                etims_logger.exception(error, exc_info=True)
                frappe.throw(
                    "Connection failed",
                    error,
                    title="Connection Error",
                )

            except asyncio.exceptions.TimeoutError as error:
                etims_logger.exception(error, exc_info=True)
                frappe.throw("Timeout Encountered", error, title="Timeout Error")


@frappe.whitelist()
def send_imported_item_request(request_data: str) -> None:
    data = json.loads(request_data)

    company_name = data["company_name"]
    headers = build_headers(company_name)

    if headers:
        server_url = get_server_url(company_name)
        route_path, last_request_date = get_route_path("ImportItemUpdateReq")
        request_date = last_request_date.strftime("%Y%m%d%H%M%S")

        if server_url and route_path:
            url = f"{server_url}{route_path}"
            declaration_date = build_datetime_from_string(
                data["declaration_date"], "%Y-%m-%d %H:%M:%S.%f"
            ).strftime("%Y%m%d")

            payload = {
                "taskCd": data["task_code"],
                "dclDe": declaration_date,
                "itemSeq": data["item_sequence"],
                "hsCd": data["hs_code"],
                "itemClsCd": data["item_classification_code"],
                "itemCd": data["item_code"],
                "imptItemSttsCd": data["import_item_status"],
                "remark": None,
                "modrNm": data["modified_by"],
                "modrId": data["modified_by"],
            }

            try:
                response = asyncio.run(make_post_request(url, payload, headers))

                if response["resultCd"] == "000":
                    frappe.msgprint(f"response: {response}")

                    update_last_request_date(response["resultDt"], route_path)

                else:
                    frappe.msgprint("Failure")

            except aiohttp.client_exceptions.ClientConnectorError as error:
                etims_logger.exception(error, exc_info=True)
                frappe.throw(
                    "Connection failed",
                    error,
                    title="Connection Error",
                )

            except asyncio.exceptions.TimeoutError as error:
                etims_logger.exception(error, exc_info=True)
                frappe.throw("Timeout Encountered", error, title="Timeout Error")


@frappe.whitelist()
def perform_notice_search(request_data: str) -> None:
    data = json.loads(request_data)

    headers = {
        "tin": data["pin"],
        "cmcKey": data["communication_key"],
        "bhfId": data["branch_id"],
    }

    route_path, last_request_date = get_route_path("NoticeSearchReq")
    request_date = last_request_date.strftime("%Y%m%d%H%M%S")

    if route_path:
        url = f"{data['server_url']}{route_path}"
        payload = {"lastReqDt": request_date}

        try:
            response = asyncio.run(make_post_request(url, payload, headers))

            if response["resultCd"] == "000":
                frappe.msgprint(f"response: {response}")
                update_last_request_date(response["resultDt"], route_path)

            else:
                handle_errors(
                    response,
                    route_path,
                    document_name=data["name"],
                    doctype=SETTINGS_DOCTYPE_NAME,
                )

        except aiohttp.client_exceptions.ClientConnectorError as error:
            etims_logger.exception(error, exc_info=True)
            frappe.throw(
                "Connection failed",
                error,
                title="Connection Error",
            )

        except asyncio.exceptions.TimeoutError as error:
            etims_logger.exception(error, exc_info=True)
            frappe.throw("Timeout Encountered", error, title="Timeout Error")


@frappe.whitelist()
def perform_code_search(request_data: str) -> None:
    data = json.loads(request_data)

    headers = {
        "tin": data["pin"],
        "cmcKey": data["communication_key"],
        "bhfId": data["branch_id"],
    }

    route_path, last_request_date = get_route_path("CodeSearchReq")
    request_date = last_request_date.strftime("%Y%m%d%H%M%S")

    if route_path:
        url = f"{data['server_url']}{route_path}"
        payload = {"lastReqDt": request_date}

        try:
            response = asyncio.run(make_post_request(url, payload, headers))

            if response["resultCd"] == "000":
                frappe.msgprint(f"response: {response}")

                update_last_request_date(response["resultDt"], route_path)

            else:
                handle_errors(
                    response,
                    route_path,
                    document_name=data["name"],
                    doctype=SETTINGS_DOCTYPE_NAME,
                )

        except aiohttp.client_exceptions.ClientConnectorError as error:
            etims_logger.exception(error, exc_info=True)
            frappe.throw(
                "Connection failed",
                error,
                title="Connection Error",
            )

        except asyncio.exceptions.TimeoutError as error:
            etims_logger.exception(error, exc_info=True)
            frappe.throw("Timeout Encountered", error, title="Timeout Error")


@frappe.whitelist()
def perform_stock_movement_search(request_data: str) -> None:
    data = json.loads(request_data)

    headers = {
        "tin": data["pin"],
        "cmcKey": data["communication_key"],
        "bhfId": data["branch_id"],
    }

    route_path, last_request_date = get_route_path("StockMoveReq")
    request_date = last_request_date.strftime("%Y%m%d%H%M%S")

    if route_path:
        url = f"{data['server_url']}{route_path}"
        payload = {"lastReqDt": request_date}

        try:
            response = asyncio.run(make_post_request(url, payload, headers))

            if response["resultCd"] == "000":
                frappe.msgprint(f"response: {response}")

                update_last_request_date(response["resultDt"], route_path)

            else:
                handle_errors(
                    response,
                    route_path,
                    document_name=data["name"],
                    doctype=SETTINGS_DOCTYPE_NAME,
                )

        except aiohttp.client_exceptions.ClientConnectorError as error:
            etims_logger.exception(error, exc_info=True)
            frappe.throw(
                "Connection failed",
                error,
                title="Connection Error",
            )

        except asyncio.exceptions.TimeoutError as error:
            etims_logger.exception(error, exc_info=True)
            frappe.throw("Timeout Encountered", error, title="Timeout Error")


def make_send_user_details_request(
    data, headers, route_path, url, payload, integration_request_name
):
    try:
        response = asyncio.run(make_post_request(url, payload, headers))

        if response["resultCd"] == "000":
            frappe.db.set_value(
                "Employee",
                data["name"],
                "custom_etims_received",
                1,
            )
            update_last_request_date(response["resultDt"], route_path)

        else:
            handle_errors(
                response,
                route_path,
                data["name"],
                "Employee",
                integration_request_name=integration_request_name.name,
            )

    except aiohttp.client_exceptions.ClientConnectorError as error:
        etims_logger.exception(error, exc_info=True)
        frappe.throw(
            "Connection failed",
            error,
            title="Connection Error",
        )

    except asyncio.exceptions.TimeoutError as error:
        etims_logger.exception(error, exc_info=True)
        frappe.throw("Timeout Encountered", error, title="Timeout Error")


def make_send_branch_customer_request(
    data, headers, route_path, url, payload, integration_request_name
):
    try:
        response = asyncio.run(make_post_request(url, payload, headers))

        if response["resultCd"] == "000":
            frappe.db.set_value(
                "Customer",
                data["name"],
                "custom_details_submitted_successfully",
                1,
            )
            update_last_request_date(response["resultDt"], route_path)

        else:
            handle_errors(
                response,
                route_path,
                data["name"],
                "Customer",
                integration_request_name=integration_request_name.name,
            )

    except aiohttp.client_exceptions.ClientConnectorError as error:
        etims_logger.exception(error, exc_info=True)
        frappe.throw(
            "Connection failed",
            error,
            title="Connection Error",
        )

    except asyncio.exceptions.TimeoutError as error:
        etims_logger.exception(error, exc_info=True)
        frappe.throw("Timeout Encountered", error, title="Timeout Error")


def make_item_registration_request(data, headers, route_path, url):
    try:
        response = asyncio.run(make_post_request(url, data, headers))

        if response["resultCd"] == "000":
            frappe.db.set_value("Item", data["name"], "custom_item_registered", 1)
            update_last_request_date(response["resultDt"], route_path)

        else:
            handle_errors(response, route_path, data["itemNm"], "Item")

    except aiohttp.client_exceptions.ClientConnectorError as error:
        etims_logger.exception(error, exc_info=True)
        frappe.throw(
            "Connection failed",
            error,
            title="Connection Error",
        )

    except asyncio.exceptions.TimeoutError as error:
        etims_logger.exception(error, exc_info=True)
        frappe.throw("Timeout Encountered", error, title="Timeout Error")


def make_customer_search_request(data, headers, route_path, url, payload) -> None:
    try:
        # TODO: Enqueue in background jobs queue
        response = asyncio.run(make_post_request(url, payload, headers))

        if response["resultCd"] == "000":
            frappe.msgprint(f"{response['resultMsg']}")

            update_last_request_date(response["resultDt"], route_path)

        else:
            handle_errors(response, route_path, data["name"], "Customer")

    except aiohttp.client_exceptions.ClientConnectorError as error:
        etims_logger.exception(error, exc_info=True)
        frappe.throw(
            "Connection failed",
            error,
            title="Connection Error",
        )

    except asyncio.exceptions.TimeoutError as error:
        etims_logger.exception(error, exc_info=True)
        frappe.throw("Timeout Encountered", error, title="Timeout Error")
