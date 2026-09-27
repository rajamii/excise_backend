import math
from django.db.models import Q
from rest_framework.response import Response
from rest_framework import status


def parse_pagination_params(request, default_page_size=10, max_page_size=100):
    """
    Extracts and validates page and page_size from request query_params.
    Returns (is_paginated, page, page_size).
    """
    query_params = getattr(request, "query_params", {}) or {}
    page_param = query_params.get("page")
    page_size_param = query_params.get("page_size")

    is_paginated = page_param is not None or page_size_param is not None
    if not is_paginated:
        return False, 1, default_page_size

    try:
        page = max(1, int(page_param or 1))
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = int(page_size_param or default_page_size)
        if page_size < 1:
            page_size = default_page_size
        elif page_size > max_page_size:
            page_size = max_page_size
    except (TypeError, ValueError):
        page_size = default_page_size

    return True, page, page_size


def paginate_queryset(request, queryset, default_page_size=10, max_page_size=100, ordering=None):
    """
    Slices a queryset using SQL LIMIT and OFFSET.
    Returns:
        (page_qs, pagination_meta)
    If not paginated:
        (queryset, None)
    If paginated:
        (page_qs, { 'count': total_count, 'page': page, 'page_size': page_size, 'total_pages': total_pages })
    """
    is_paginated, page, page_size = parse_pagination_params(request, default_page_size, max_page_size)
    if not is_paginated:
        return queryset, None

    if ordering:
        queryset = queryset.order_by(*ordering)

    total_count = queryset.count()
    total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
    offset = (page - 1) * page_size
    page_qs = queryset[offset : offset + page_size]

    pagination_meta = {
        "count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
    return page_qs, pagination_meta


def apply_query_filters(request, queryset, search_fields=None, date_field="created_at"):
    """
    Applies search (term across search_fields) and date/month/year filters to a queryset.
    """
    query_params = getattr(request, "query_params", {}) or {}

    term = (query_params.get("search") or query_params.get("q") or "").strip()
    if term and search_fields:
        search_q = Q()
        for field in search_fields:
            search_q |= Q(**{f"{field}__icontains": term})
        queryset = queryset.filter(search_q)

    date_val = (query_params.get("date") or "").strip()
    if date_val:
        queryset = queryset.filter(**{f"{date_field}__date": date_val})

    month_val = (query_params.get("month") or "").strip()
    if month_val:
        if "-" in month_val:
            try:
                y_str, m_str = month_val.split("-")[:2]
                queryset = queryset.filter(**{f"{date_field}__year": int(y_str), f"{date_field}__month": int(m_str)})
            except (ValueError, TypeError):
                pass
        else:
            try:
                queryset = queryset.filter(**{f"{date_field}__month": int(month_val)})
            except (ValueError, TypeError):
                pass

    year_val = (query_params.get("year") or "").strip()
    if year_val:
        try:
            queryset = queryset.filter(**{f"{date_field}__year": int(year_val)})
        except (ValueError, TypeError):
            pass

    return queryset


def build_paginated_response(page_qs, serializer_class_or_fn, pagination_meta):
    """
    Builds a DRF Response.
    If pagination_meta is None, returns serialized list.
    If pagination_meta is provided, returns { **pagination_meta, 'results': serialized_data }.
    """
    if hasattr(serializer_class_or_fn, "many_init") or (isinstance(serializer_class_or_fn, type) and issubclass(serializer_class_or_fn, object)):
        try:
            serialized_data = serializer_class_or_fn(page_qs, many=True).data
        except TypeError:
            serialized_data = [serializer_class_or_fn(obj) for obj in page_qs]
    elif callable(serializer_class_or_fn):
        serialized_data = [serializer_class_or_fn(obj) for obj in page_qs]
    else:
        serialized_data = list(page_qs)

    if pagination_meta is None:
        return Response(serialized_data, status=status.HTTP_200_OK)

    payload = {
        **pagination_meta,
        "results": serialized_data,
    }
    return Response(payload, status=status.HTTP_200_OK)
