"""
routes/cantina.py
=================
Módulo de cantina: produtos, pedidos e caixa.
"""
from datetime import date, datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_cantina
from app.db.models import CantinCashFlow, CantinOrder, CantinOrderItem, CantinProduct, User
from app.db.session import get_db

router = APIRouter(prefix="/cantina", tags=["Cantina"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    category: Optional[str] = None
    stock: int = 0
    min_stock: int = 5
    active: bool = True
    image_url: Optional[str] = None
    pdv_id: int = 1


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    stock: Optional[int] = None
    min_stock: Optional[int] = None
    active: Optional[bool] = None
    image_url: Optional[str] = None


class StockAdjust(BaseModel):
    stock: int


class OrderItemIn(BaseModel):
    product_id: int
    quantity: int


class OrderCreate(BaseModel):
    items: List[OrderItemIn]
    payment_method: Optional[str] = None
    notes: Optional[str] = None
    pdv_id: int = 1


class OrderStatusUpdate(BaseModel):
    status: str


class CashFlowCreate(BaseModel):
    type: str          # "entrada" | "saida"
    amount: float
    description: str
    payment_method: Optional[str] = None
    pdv_id: int = 1


class RefundRequest(BaseModel):
    reason: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _users_map(db: Session, *id_sets) -> dict:
    """Retorna {user_id: user_name} para todos os IDs fornecidos."""
    ids = set()
    for s in id_sets:
        ids.update(i for i in s if i)
    if not ids:
        return {}
    users = db.query(User.id, User.name).filter(User.id.in_(ids)).all()
    return {u.id: u.name for u in users}


def _product_out(p: CantinProduct) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "price": float(p.price),
        "category": p.category,
        "stock": p.stock,
        "min_stock": p.min_stock,
        "active": p.active,
        "image_url": p.image_url,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "pdv_id": p.pdv_id if hasattr(p, "pdv_id") and p.pdv_id is not None else 1,
    }


def _item_out(i: CantinOrderItem) -> dict:
    return {
        "id": i.id,
        "product_id": i.product_id,
        "product_name": i.product_name,
        "unit_price": float(i.unit_price),
        "quantity": i.quantity,
        "subtotal": float(i.subtotal),
    }


def _order_out(o: CantinOrder, users: dict = None) -> dict:
    u = users or {}
    return {
        "id": o.id,
        "order_number": o.order_number,
        "status": o.status,
        "payment_method": o.payment_method,
        "total": float(o.total),
        "notes": o.notes,
        "created_by": o.created_by,
        "created_by_name": u.get(o.created_by),
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "refunded_at": o.refunded_at.isoformat() if o.refunded_at else None,
        "refunded_by": o.refunded_by,
        "refunded_by_name": u.get(o.refunded_by) if o.refunded_by else None,
        "refund_reason": o.refund_reason,
        "items": [_item_out(i) for i in (o.items or [])],
        "pdv_id": o.pdv_id if hasattr(o, "pdv_id") and o.pdv_id is not None else 1,
    }


def _cashflow_out(c: CantinCashFlow, users: dict = None) -> dict:
    u = users or {}
    return {
        "id": c.id,
        "type": c.type,
        "amount": float(c.amount),
        "description": c.description,
        "payment_method": c.payment_method,
        "created_by": c.created_by,
        "created_by_name": u.get(c.created_by),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "pdv_id": c.pdv_id if hasattr(c, "pdv_id") and c.pdv_id is not None else 1,
    }


# Ajustar para fuso horário local (ex: Brasil, UTC-3).
LOCAL_TZ = timezone(timedelta(hours=-3))


def _today_start():
    now = datetime.now(LOCAL_TZ)
    local_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(timezone.utc)


def _today_end():
    now = datetime.now(LOCAL_TZ)
    local_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    return local_end.astimezone(timezone.utc)


def _parse_date_range(date_from: Optional[str], date_to: Optional[str]):
    """Retorna (dt_from, dt_to) como datetime UTC ou (None, None) se não informado."""
    dt_from = dt_to = None
    if date_from:
        try:
            d = date.fromisoformat(date_from)
            local_from = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=LOCAL_TZ)
            dt_from = local_from.astimezone(timezone.utc)
        except ValueError:
            pass
    if date_to:
        try:
            d = date.fromisoformat(date_to)
            local_to = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=LOCAL_TZ)
            dt_to = local_to.astimezone(timezone.utc)
        except ValueError:
            pass
    return dt_from, dt_to


def _next_order_number(db: Session) -> int:
    max_number = db.query(func.max(CantinOrder.order_number)).scalar() or 0
    return int(max_number) + 1


# ---------------------------------------------------------------------------
# PRODUTOS
# ---------------------------------------------------------------------------

@router.get("/products")
def list_products(
    active: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    pdv_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(CantinProduct)
    if active is not None:
        q = q.filter(CantinProduct.active == active)
    if category:
        q = q.filter(CantinProduct.category == category)
    if pdv_id is not None:
        q = q.filter(CantinProduct.pdv_id == pdv_id)
    return [_product_out(p) for p in q.order_by(CantinProduct.category, CantinProduct.name).all()]


@router.post("/products", status_code=201)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_cantina),
):
    p = CantinProduct(
        name=data.name,
        description=data.description,
        price=data.price,
        category=data.category,
        stock=data.stock,
        min_stock=data.min_stock,
        active=data.active,
        image_url=data.image_url,
        pdv_id=data.pdv_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _product_out(p)


@router.put("/products/{product_id}")
def update_product(
    product_id: int,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_cantina),
):
    p = db.query(CantinProduct).filter(CantinProduct.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    return _product_out(p)


@router.put("/products/{product_id}/stock")
def update_stock(
    product_id: int,
    data: StockAdjust,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_cantina),
):
    p = db.query(CantinProduct).filter(CantinProduct.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    p.stock = data.stock
    db.commit()
    db.refresh(p)
    return _product_out(p)


@router.delete("/products/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_cantina),
):
    p = db.query(CantinProduct).filter(CantinProduct.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    db.delete(p)
    db.commit()


# ---------------------------------------------------------------------------
# PEDIDOS
# ---------------------------------------------------------------------------

@router.get("/orders")
def list_orders(
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    pdv_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dt_from, dt_to = _parse_date_range(date_from, date_to)
    if not dt_from and not dt_to:
        dt_from = _today_start()
        dt_to = _today_end()
    q = db.query(CantinOrder)
    if dt_from:
        q = q.filter(CantinOrder.created_at >= dt_from)
    if dt_to:
        q = q.filter(CantinOrder.created_at <= dt_to)
    if status:
        q = q.filter(CantinOrder.status == status)
    if pdv_id is not None:
        q = q.filter(CantinOrder.pdv_id == pdv_id)
    orders = q.order_by(CantinOrder.id.desc()).all()
    uid_sets = (
        {o.created_by for o in orders},
        {o.refunded_by for o in orders},
    )
    users = _users_map(db, *uid_sets)
    return [_order_out(o, users) for o in orders]


@router.post("/orders", status_code=201)
def create_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_cantina),
):
    if not data.items:
        raise HTTPException(status_code=400, detail="Pedido sem itens")

    total = 0.0
    order_items = []
    for item_in in data.items:
        product = db.query(CantinProduct).filter(CantinProduct.id == item_in.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Produto {item_in.product_id} não encontrado")
        if not product.active:
            raise HTTPException(status_code=400, detail=f"Produto '{product.name}' está inativo")
        if product.stock < item_in.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Estoque insuficiente para '{product.name}': disponível {product.stock}",
            )
        subtotal = float(product.price) * item_in.quantity
        total += subtotal
        order_items.append((product, item_in.quantity, subtotal))

    order = CantinOrder(
        order_number=_next_order_number(db),
        status="paid" if data.payment_method else "pending",
        payment_method=data.payment_method,
        total=total,
        notes=data.notes,
        created_by=current_user.id,
        pdv_id=data.pdv_id,
    )
    db.add(order)
    db.flush()

    for product, qty, subtotal in order_items:
        oi = CantinOrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            unit_price=float(product.price),
            quantity=qty,
            subtotal=subtotal,
        )
        db.add(oi)
        product.stock -= qty

    db.commit()
    db.refresh(order)
    return _order_out(order)


@router.put("/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_cantina),
):
    order = db.query(CantinOrder).filter(CantinOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    if data.status == "cancelled" and order.status != "cancelled":
        # Devolver estoque
        for item in order.items:
            if item.product_id:
                product = db.query(CantinProduct).filter(CantinProduct.id == item.product_id).first()
                if product:
                    product.stock += item.quantity

    order.status = data.status
    db.commit()
    db.refresh(order)
    return _order_out(order)


@router.post("/orders/{order_id}/refund")
def refund_order(
    order_id: int,
    data: RefundRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_cantina),
):
    order = db.query(CantinOrder).filter(CantinOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.status != "paid":
        raise HTTPException(status_code=400, detail="Apenas pedidos pagos podem ser estornados")
    if order.status == "refunded":
        raise HTTPException(status_code=400, detail="Pedido já foi estornado")

    # Devolver estoque
    for item in order.items:
        if item.product_id:
            product = db.query(CantinProduct).filter(CantinProduct.id == item.product_id).first()
            if product:
                product.stock += item.quantity

    # Atualizar pedido
    order.status = "refunded"
    order.refunded_at = datetime.now(timezone.utc)
    order.refunded_by = current_user.id
    order.refund_reason = data.reason

    db.commit()
    db.refresh(order)
    users = _users_map(db, {order.created_by}, {order.refunded_by})
    return _order_out(order, users)


@router.delete("/orders/{order_id}", status_code=204)
def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_cantina),
):
    order = db.query(CantinOrder).filter(CantinOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.status not in ("cancelled", "refunded"):
        for item in order.items:
            if item.product_id:
                product = db.query(CantinProduct).filter(CantinProduct.id == item.product_id).first()
                if product:
                    product.stock += item.quantity
    db.delete(order)
    db.commit()


# ---------------------------------------------------------------------------
# CAIXA
# ---------------------------------------------------------------------------

@router.get("/cash")
def get_cash_summary(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    pdv_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dt_from, dt_to = _parse_date_range(date_from, date_to)
    if not dt_from and not dt_to:
        dt_from = _today_start()
        dt_to = _today_end()

    def _order_q():
        q = db.query(CantinOrder)
        if dt_from:
            q = q.filter(CantinOrder.created_at >= dt_from)
        if dt_to:
            q = q.filter(CantinOrder.created_at <= dt_to)
        if pdv_id is not None:
            q = q.filter(CantinOrder.pdv_id == pdv_id)
        return q

    def _flow_q():
        q = db.query(CantinCashFlow)
        if dt_from:
            q = q.filter(CantinCashFlow.created_at >= dt_from)
        if dt_to:
            q = q.filter(CantinCashFlow.created_at <= dt_to)
        if pdv_id is not None:
            q = q.filter(CantinCashFlow.pdv_id == pdv_id)
        return q

    paid_orders = _order_q().filter(CantinOrder.status == "paid").all()
    refunded_orders = _order_q().filter(CantinOrder.status == "refunded").all()

    total_dinheiro = sum(float(o.total) for o in paid_orders if o.payment_method == "dinheiro")
    total_pix = sum(float(o.total) for o in paid_orders if o.payment_method == "pix")
    total_vendas = sum(float(o.total) for o in paid_orders)
    total_refunded = sum(float(o.total) for o in refunded_orders)

    flows = _flow_q().all()
    total_entradas = sum(float(f.amount) for f in flows if f.type == "entrada")
    # Exclui cashflows de estorno (gerados por versões antigas) para não contar duplo
    total_saidas = sum(
        float(f.amount) for f in flows
        if f.type == "saida" and "Estorno" not in (f.description or "")
    )

    all_orders = _order_q().all()
    pending = sum(1 for o in all_orders if o.status == "pending")
    cancelled = sum(1 for o in all_orders if o.status == "cancelled")

    return {
        "total_vendas": total_vendas,
        "total_dinheiro": total_dinheiro,
        "total_pix": total_pix,
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
        "total_refunded": total_refunded,
        "saldo": total_vendas - total_refunded + total_entradas - total_saidas,
        "orders_count": len(all_orders),
        "orders_paid": len(paid_orders),
        "orders_pending": pending,
        "orders_cancelled": cancelled,
        "orders_refunded": len(refunded_orders),
    }


@router.get("/cash/flow")
def list_cash_flow(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    pdv_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dt_from, dt_to = _parse_date_range(date_from, date_to)
    if not dt_from and not dt_to:
        dt_from = _today_start()
        dt_to = _today_end()
    q = db.query(CantinCashFlow)
    if dt_from:
        q = q.filter(CantinCashFlow.created_at >= dt_from)
    if dt_to:
        q = q.filter(CantinCashFlow.created_at <= dt_to)
    if pdv_id is not None:
        q = q.filter(CantinCashFlow.pdv_id == pdv_id)
    flows = q.order_by(CantinCashFlow.created_at).all()
    users = _users_map(db, {f.created_by for f in flows})
    return [_cashflow_out(f, users) for f in flows]


@router.post("/cash/flow", status_code=201)
def add_cash_flow(
    data: CashFlowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_cantina),
):
    if data.type not in ("entrada", "saida"):
        raise HTTPException(status_code=400, detail="Tipo deve ser 'entrada' ou 'saida'")
    flow = CantinCashFlow(
        type=data.type,
        amount=data.amount,
        description=data.description,
        payment_method=data.payment_method,
        created_by=current_user.id,
        pdv_id=data.pdv_id,
    )
    db.add(flow)
    db.commit()
    db.refresh(flow)
    users = _users_map(db, {flow.created_by})
    return _cashflow_out(flow, users)


# ---------------------------------------------------------------------------
# CONSOLIDADO (ambos PDVs)
# ---------------------------------------------------------------------------

@router.get("/cash/consolidated")
def get_cash_consolidated(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dt_from, dt_to = _parse_date_range(date_from, date_to)
    if not dt_from and not dt_to:
        dt_from = _today_start()
        dt_to = _today_end()

    def _summary_for_pdv(pdv: int) -> dict:
        def oq():
            q = db.query(CantinOrder)
            if dt_from:
                q = q.filter(CantinOrder.created_at >= dt_from)
            if dt_to:
                q = q.filter(CantinOrder.created_at <= dt_to)
            q = q.filter(CantinOrder.pdv_id == pdv)
            return q

        def fq():
            q = db.query(CantinCashFlow)
            if dt_from:
                q = q.filter(CantinCashFlow.created_at >= dt_from)
            if dt_to:
                q = q.filter(CantinCashFlow.created_at <= dt_to)
            q = q.filter(CantinCashFlow.pdv_id == pdv)
            return q

        paid = oq().filter(CantinOrder.status == "paid").all()
        refunded = oq().filter(CantinOrder.status == "refunded").all()
        all_orders = oq().all()
        flows = fq().all()
        total_vendas = sum(float(o.total) for o in paid)
        total_dinheiro = sum(float(o.total) for o in paid if o.payment_method == "dinheiro")
        total_pix = sum(float(o.total) for o in paid if o.payment_method == "pix")
        total_refunded = sum(float(o.total) for o in refunded)
        total_entradas = sum(float(f.amount) for f in flows if f.type == "entrada")
        total_saidas = sum(
            float(f.amount) for f in flows
            if f.type == "saida" and "Estorno" not in (f.description or "")
        )
        return {
            "total_vendas": total_vendas,
            "total_dinheiro": total_dinheiro,
            "total_pix": total_pix,
            "total_entradas": total_entradas,
            "total_saidas": total_saidas,
            "total_refunded": total_refunded,
            "saldo": total_vendas - total_refunded + total_entradas - total_saidas,
            "orders_count": len(all_orders),
            "orders_paid": len(paid),
            "orders_pending": sum(1 for o in all_orders if o.status == "pending"),
            "orders_cancelled": sum(1 for o in all_orders if o.status == "cancelled"),
            "orders_refunded": len(refunded),
        }

    s1 = _summary_for_pdv(1)
    s2 = _summary_for_pdv(2)
    total = {k: s1[k] + s2[k] for k in s1}
    return {"pdv1": s1, "pdv2": s2, "total": total}


# ---------------------------------------------------------------------------
# RELATÓRIO
# ---------------------------------------------------------------------------

@router.get("/report")
def get_report(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    pdv_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dt_from, dt_to = _parse_date_range(date_from, date_to)
    if not dt_from and not dt_to:
        dt_from = _today_start()
        dt_to = _today_end()

    def _order_q():
        q = db.query(CantinOrder).filter(CantinOrder.status == "paid")
        if dt_from:
            q = q.filter(CantinOrder.created_at >= dt_from)
        if dt_to:
            q = q.filter(CantinOrder.created_at <= dt_to)
        if pdv_id is not None:
            q = q.filter(CantinOrder.pdv_id == pdv_id)
        return q

    paid_orders = _order_q().all()

    total_vendas = sum(float(o.total) for o in paid_orders)
    total_dinheiro = sum(float(o.total) for o in paid_orders if o.payment_method == "dinheiro")
    total_pix = sum(float(o.total) for o in paid_orders if o.payment_method == "pix")

    # Produtos mais vendidos (apenas pedidos pagos, excluindo estornados)
    product_sales: dict = {}
    for order in paid_orders:
        for item in order.items:
            key = item.product_name
            if key not in product_sales:
                product_sales[key] = {"name": key, "qty": 0, "total": 0.0}
            product_sales[key]["qty"] += item.quantity
            product_sales[key]["total"] += float(item.subtotal)

    top_products = sorted(product_sales.values(), key=lambda x: x["qty"], reverse=True)

    # Vendas por categoria
    category_sales: dict = {}
    for order in paid_orders:
        for item in order.items:
            product = db.query(CantinProduct).filter(CantinProduct.id == item.product_id).first()
            cat = (product.category if product else None) or "Outros"
            if cat not in category_sales:
                category_sales[cat] = {"category": cat, "qty": 0, "total": 0.0}
            category_sales[cat]["qty"] += item.quantity
            category_sales[cat]["total"] += float(item.subtotal)

    flow_q = db.query(CantinCashFlow)
    if dt_from:
        flow_q = flow_q.filter(CantinCashFlow.created_at >= dt_from)
    if dt_to:
        flow_q = flow_q.filter(CantinCashFlow.created_at <= dt_to)
    if pdv_id is not None:
        flow_q = flow_q.filter(CantinCashFlow.pdv_id == pdv_id)
    flows = flow_q.order_by(CantinCashFlow.created_at).all()

    users = _users_map(db, {f.created_by for f in flows})

    return {
        "date": (dt_from.date().isoformat() if dt_from else None),
        "total_vendas": total_vendas,
        "total_dinheiro": total_dinheiro,
        "total_pix": total_pix,
        "orders_paid": len(paid_orders),
        "top_products": top_products,
        "category_sales": list(category_sales.values()),
        "cash_flow": [_cashflow_out(f, users) for f in flows],
    }
