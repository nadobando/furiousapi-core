import operator
from typing import TypedDict

from furiousapi.rql.exceptions import RQLFilterNotAllowedError, RQLSortNotAllowedError

ALL_TEST_CASES: list[dict] = [
    {
        "params": ("select(*)", {"fields": {"*": None}, "filter": [], "sort": []}),
        "id": "select_all_fields",
    },
    {
        "params": ("select(id)", {"fields": {"id": None}, "filter": [], "sort": []}),
        "id": "select_single_field",
    },
    {
        "params": ("select(id,name)", {"fields": {"id": None, "name": None}, "filter": [], "sort": []}),
        "id": "select_multiple_fields",
    },
    {
        "params": ("select(parent[child])", {"fields": {"parent": {"child": None}}, "filter": [], "sort": []}),
        "id": "select_nested_field",
    },
    {
        "params": (
            "select(parent[*,child])",
            {"fields": {"parent": {"*": None, "child": None}}, "filter": [], "sort": []},
        ),
        "id": "select_nested_field_with_wildcard",
    },
    {
        "params": (
            "select(id,parent1[child[id,subchild]])",
            {"fields": {"id": None, "parent1": {"child": {"id": None, "subchild": None}}}, "filter": [], "sort": []},
        ),
        "id": "select_deep_nested_field",
    },
    {
        "params": ("select(id);sort(+id)", {"fields": {"id": None}, "filter": [], "sort": [("id", operator.pos)]}),
        "id": "sort_single_field_asc",
    },
    {
        "params": ("select(id);sort(-id)", {"fields": {"id": None}, "filter": [], "sort": [("id", operator.neg)]}),
        "id": "sort_single_field_desc",
    },
    {
        "params": (
            "select(id);sort(+name,-score)",
            {"fields": {"id": None}, "filter": [], "sort": [("name", operator.pos), ("score", operator.neg)]},
        ),
        "id": "sort_multiple_fields",
    },
    {
        "params": (
            "select(id);sort(+parent.child.name)",
            {"fields": {"id": None}, "filter": [], "sort": [("parent.child.name", operator.pos)]},
        ),
        "id": "sort_on_nested_field",
    },
    {
        "params": (
            "select(id);distinct(id)",
            {"fields": {"id": None}, "distinct": ["id"], "filter": [], "sort": []},
        ),
        "id": "distinct_single_field",
    },
    {
        "params": (
            "select(id);eq(name,'abc')",
            {"fields": {"id": None}, "filter": [["__eq__", "name", "abc"]], "sort": []},
        ),
        "id": "filter_eq_constant",
    },
    {
        "params": (
            "select(id);eq(status,null)",
            {"fields": {"id": None}, "filter": [["__eq__", "status", None]], "sort": []},
        ),
        "id": "filter_eq_null",
    },
    {
        "params": (
            "select(id);eq(is_active,true)",
            {"fields": {"id": None}, "filter": [["__eq__", "is_active", True]], "sort": []},
        ),
        "id": "filter_eq_boolean_true",
    },
    {
        "params": (
            "select(id);like(description,'%abc%')",
            {"fields": {"id": None}, "filter": [["like", "description", "%abc%"]], "sort": []},
        ),
        "id": "filter_like_pattern",
    },
    {
        "params": (
            "select(id);in(id,(1,2,3))",
            {"fields": {"id": None}, "filter": [["__contains__", "id", [1, 2, 3]]], "sort": []},
        ),
        "id": "filter_in_values",
    },
    {
        "params": (
            "select(id);not(eq(name,'abc'))",
            {"fields": {"id": None}, "filter": [["__not__", ["__eq__", "name", "abc"]]], "sort": []},
        ),
        "id": "filter_not_eq",
    },
    {
        "params": (
            "select(id);not(and(eq(score,123),eq(name,'abc')))",
            {
                "fields": {"id": None},
                "filter": [["__not__", ["__and__", [["__eq__", "score", 123], ["__eq__", "name", "abc"]]]]],
                "sort": [],
            },
        ),
        "id": "filter_not_and",
    },
    {
        "params": (
            "select(id);or(eq(type,'A'),eq(type,'B'))",
            {
                "fields": {"id": None},
                "filter": [["__or__", [["__eq__", "type", "A"], ["__eq__", "type", "B"]]]],
                "sort": [],
            },
        ),
        "id": "filter_or_conditions",
    },
    {
        "params": (
            "select(id);and(eq(age,30),eq(score,100))",
            {
                "fields": {"id": None},
                "filter": [["__and__", [["__eq__", "age", 30], ["__eq__", "score", 100]]]],
                "sort": [],
            },
        ),
        "id": "filter_and_conditions",
    },
    {
        "params": (
            "select(id);eq(parent.child.name,'abc')",
            {"fields": {"id": None}, "filter": [["__eq__", "parent.child.name", "abc"]], "sort": []},
        ),
        "id": "filter_nested_fields",
    },
    {
        "params": (
            "select(id);and(or(eq(level,1),eq(level,2)),eq(enabled,true))",
            {
                "fields": {"id": None},
                "filter": [
                    [
                        "__and__",
                        [["__or__", [["__eq__", "level", 1], ["__eq__", "level", 2]]], ["__eq__", "enabled", True]],
                    ]
                ],
                "sort": [],
            },
        ),
        "id": "filter_and_or_nested",
    },
    {
        "params": (
            "select(id);eq(name,'abc');sort(+id)",
            {"fields": {"id": None}, "filter": [["__eq__", "name", "abc"]], "sort": [("id", operator.pos)]},
        ),
        "id": "select_with_sort_and_filter",
    },
    {
        "params": (
            "select(id,parent[*]);sort(+parent.child.name)",
            {
                "fields": {"id": None, "parent": {"*": None}},
                "filter": [],
                "sort": [("parent.child.name", operator.pos)],
            },
        ),
        "id": "select_nested_with_sort_on_nested",
    },
]


class ParamDictError(TypedDict):
    params: tuple[str, type[Exception]]
    id: str


ERROR_CASES: list[ParamDictError] = [
    {
        "params": (
            "sort(+name)",
            RQLSortNotAllowedError,
        ),
        "id": "sort_not_in_allowed_list",
    },
    {
        "params": (
            "sort(+forbidden_sort)",
            RQLSortNotAllowedError,
        ),
        "id": "sort_explicitly_denied_field",
    },
    {
        "params": (
            "eq(name,'x')",
            RQLFilterNotAllowedError,
        ),
        "id": "filter_operator_not_in_allowed_list",
    },
    {
        "params": (
            "ilike(name,'x')",
            RQLFilterNotAllowedError,
        ),
        "id": "filter_explicitly_denied_operator",
    },
]
