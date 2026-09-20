from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal, init_db
from app.ledger_models import Invoice, LedgerRequest, MoneyMovement
from app.main import app
from app.models import Customer, Order, Product
from app.services import ledger_service, order_service


def post(client, path, payload, key=None):
    return client.post('/api/ledger' + path, json=payload, headers={'Idempotency-Key': key or str(uuid4())})


def opening(client, amount='0'):
    response = post(client, '/opening', {'amount': amount})
    assert response.status_code == 200, response.text


def sale(client, amount='1000', received='400', **extra):
    data = {'customer_id': 1, 'description': 'Groceries', 'amount': amount, 'received': received,
            'due_date': str(ledger_service.today() + timedelta(days=2)), **extra}
    result = post(client, '/invoices', data)
    assert result.status_code == 201, result.text
    return result.json()


def test_partial_collection_changes_funds_not_sales(client):
    opening(client, '500')
    invoice = sale(client)
    assert invoice['outstanding_paise'] == 60000
    response = post(client, f"/invoices/{invoice['id']}/payments", {'amount': '200', 'method': 'upi'})
    assert response.status_code == 200
    assert response.json()['outstanding_paise'] == 40000
    summary = client.get('/api/ledger/summary').json()
    assert summary['sales_paise'] == 100000
    assert summary['available_paise'] == 110000
    assert summary['receivables_paise'] == 40000
    ledger = client.get('/api/ledger/customers/1').json()
    assert [e['balance_paise'] for e in ledger['entries']] == [100000, 60000, 40000]
    reminder = client.get(f"/api/ledger/invoices/{invoice['id']}/reminder").json()
    assert '400.00' in reminder['text']


def test_exact_money_and_full_payment(client):
    opening(client, '0.10')
    invoice = sale(client, amount='0.30', received='0.10')
    response = post(client, f"/invoices/{invoice['id']}/payments", {'amount': '0.20'})
    assert response.json()['outstanding_paise'] == 0
    assert client.get('/api/ledger/summary').json()['available_paise'] == 40
    assert client.get(f"/api/ledger/invoices/{invoice['id']}/reminder").status_code == 409


@pytest.mark.parametrize('amount', ['0.001', '-1', 'NaN', 'Infinity', '1000000000'])
def test_invalid_precision_or_amount_rejected(client, amount):
    assert post(client, '/opening', {'amount': amount}).status_code == 422


def test_credit_requires_due_date_and_overpayment_rolls_back(client, db):
    opening(client)
    assert post(client, '/invoices', {'customer_id': 1, 'description': 'Milk', 'amount': '100'}).status_code == 422
    invoice = sale(client)
    response = post(client, f"/invoices/{invoice['id']}/payments", {'amount': '601'})
    assert response.status_code == 409
    assert db.scalar(select(func.count(MoneyMovement.id))) == 1
    assert client.get('/api/ledger/summary').json()['receivables_paise'] == 60000


def test_duplicate_request_replays_and_changed_payload_conflicts(client, db):
    opening(client)
    key = str(uuid4())
    body = {'customer_id': 1, 'description': 'Milk', 'amount': '10', 'received': '10'}
    first = post(client, '/invoices', body, key)
    second = post(client, '/invoices', body, key)
    assert first.json() == second.json()
    assert db.scalar(select(func.count(Invoice.id))) == 1
    assert db.scalar(select(func.count(MoneyMovement.id))) == 1
    assert post(client, '/invoices', {**body, 'description': 'Changed'}, key).status_code == 409


def test_concurrent_collections_cannot_overpay(client):
    opening(client)
    invoice = sale(client, amount='100', received='0')
    def collect(_):
        with TestClient(app) as other:
            return post(other, f"/invoices/{invoice['id']}/payments", {'amount': '75'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(collect, range(2)))
    assert codes == [200, 409]
    assert client.get('/api/ledger/summary').json()['receivables_paise'] == 2500


def test_concurrent_replay_creates_one_payment(client):
    opening(client)
    invoice = sale(client, amount='100', received='0')
    key = str(uuid4())
    def collect(_):
        with TestClient(app) as other:
            return post(other, f"/invoices/{invoice['id']}/payments", {'amount': '75'}, key).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(collect, range(2)))
    assert responses[0] == responses[1]
    assert client.get('/api/ledger/summary').json()['available_paise'] == 7500


def test_supplier_shortfall_expenses_and_payments(client):
    opening(client, '12000')
    bill = post(client, '/payables', {'supplier': 'Distributor', 'description': 'Stock', 'amount': '20000',
                                    'due_date': str(ledger_service.today() + timedelta(days=2))}).json()
    sale(client, '10000', '0', due_date=str(ledger_service.today() - timedelta(days=1)))
    summary = client.get('/api/ledger/summary?horizon=3').json()
    assert summary['shortfall_paise'] == 800000
    assert summary['overdue_paise'] == 1000000
    assert summary['available_paise'] == 1200000
    response = post(client, f"/payables/{bill['id']}/payments", {'amount': '1000', 'method': 'bank'})
    assert response.json()['outstanding_paise'] == 1900000
    assert post(client, '/expenses', {'amount': '100', 'description': 'Transport'}).status_code == 201
    summary = client.get('/api/ledger/summary?horizon=3').json()
    assert summary['available_paise'] == 1090000
    assert summary['shortfall_paise'] == 810000
    assert post(client, f"/payables/{bill['id']}/payments", {'amount': '19001'}).status_code == 409


def test_due_today_is_not_overdue_and_window_is_half_open(client):
    opening(client)
    sale(client, '100', '0', due_date=str(ledger_service.today()))
    sale(client, '200', '0', due_date=str(ledger_service.today() + timedelta(days=7)))
    summary = client.get('/api/ledger/summary').json()
    assert summary['overdue_paise'] == 0
    assert summary['upcoming_paise'] == 10000


def test_opening_receivables_are_not_sales_or_funds(client):
    opening(client, '50')
    sale(client, '100', '0', kind='opening_receivable')
    summary = client.get('/api/ledger/summary').json()
    assert summary['sales_paise'] == 0
    assert summary['available_paise'] == 5000
    assert summary['receivables_paise'] == 10000


def test_opening_is_explicit_and_one_time(client):
    assert client.get('/api/ledger/summary').json()['available_paise'] is None
    assert post(client, '/expenses', {'amount': '10', 'description': 'Travel'}).status_code == 409
    opening(client)
    assert post(client, '/opening', {'amount': '100'}).status_code == 409


def test_customer_creation_and_duplicate_phone(client):
    body = {'name': 'New Customer', 'phone': '9123456789'}
    first = post(client, '/customers', body)
    assert first.status_code == 201
    assert post(client, '/customers', body).status_code == 409
    assert post(client, '/customers', {**body, 'name': '   ', 'phone': '123'}).status_code == 422


def test_additive_bootstrap_preserves_orders_and_link_does_not_deduct_stock(client, db):
    order = order_service.create_order(db, 1, [{'product_id': 1, 'quantity': 1}], delivery=False).order
    stock = db.get(Product, 1).stock_quantity
    init_db()
    assert db.get(Order, order.id) is not None
    assert db.scalar(select(func.count(Customer.id))) == 4
    assert client.get('/api/ledger/summary').json()['unrecorded_orders'] == 1
    opening(client)
    sale(client, str(order.total), '0', order_id=order.id)
    db.expire_all()
    assert db.get(Product, 1).stock_quantity == stock
    assert client.get('/api/ledger/summary').json()['unrecorded_orders'] == 0
    response = post(client, '/invoices', {'customer_id': 1, 'description': 'Duplicate', 'amount': str(order.total),
                                         'received': str(order.total), 'order_id': order.id})
    assert response.status_code == 409


def test_failure_rolls_back_invoice_receipt_and_retry_record(client, db, monkeypatch):
    opening(client)
    def fail(*args, **kwargs):
        raise RuntimeError('Simulated failure after receipt write')
    monkeypatch.setattr(ledger_service, 'invoice_data', fail)
    key = str(uuid4())
    with pytest.raises(RuntimeError):
        post(client, '/invoices', {'customer_id': 1, 'description': 'Milk', 'amount': '10', 'received': '10'}, key)
    with SessionLocal() as check:
        assert check.scalar(select(func.count(Invoice.id))) == 0
        assert check.scalar(select(func.count(MoneyMovement.id))) == 0
        assert check.get(LedgerRequest, key) is None


def test_ledger_pagination_keeps_running_balance(client):
    opening(client)
    sale(client)
    data = client.get('/api/ledger/customers/1?offset=1&limit=1').json()
    assert data['total'] == 2
    assert data['entries'][0]['balance_paise'] == 60000
