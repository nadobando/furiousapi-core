from typing import Final

from lark import Lark

EQ: Final = "eq"
NE: Final = "ne"

GT: Final = "gt"
LT: Final = "lt"

GE: Final = "ge"
LE: Final = "le"

IN: Final = "in"
CONTAINS: Final = "in"

OR: Final = "or"
AND: Final = "and"

NOT: Final = "not"

COMPARATOR_MAPPING = {
    EQ: "__eq__",
    NE: "__ne__",
    GT: "__gt__",
    GE: "__ge__",
    LT: "__lt__",
    LE: "__le__",
    IN: "__contains__",
    CONTAINS: "__contains__",
    OR: "__or__",
    AND: "__and__",
    NOT: "__not__",
}

# Literal formats as string templates
DATETIME = r"/\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?([Zz]|[+-]\d{2}:\d{2})?/"
DATE = r"/\d{4}-\d{2}-\d{2}/"
TIME = r"/\d{2}:\d{2}(:\d{2})?/"
TRUE = '"true" | "True" | "TRUE"'
FALSE = '"false" | "False" | "FALSE"'

# ---- Core Tokens and Common Rules ----
CORE = r"""
_L_PAREN: "("
_R_PAREN: ")"
_L_BRACKET: "["
_R_BRACKET: "]"
_COMMA: ","
_EQUALITY: "="
_SEMICOLON: ";"
_L_BRACE: "("
_R_BRACE: ")"

STAR: "*"
PROP: /[a-zA-Z_][\w\-\.]*/
PROP_NO_DOT: /[a-zA-Z_][\w\-]*/
QUOTED_VAL: /"[^"]*"/ | /'[^']*'/
UNQUOTED_VAL: /[\w\-\*\+\\][\w\.\s\-\:\+\@\*\\]*/
"""
# ---- Property Parsing ----
PROP_RULES = r"""
prop: _filter_terms | _transformation_prop_terms | PROP
"""
# ---- Base Structure ----
START = r"""
start: _top_term?
_top_term: _term (_SEMICOLON _term)* _SEMICOLON?
_term: filter | transformation | _L_BRACE _term _R_BRACE
"""

# ---- Values and Literals ----
LITERALS = r"""
transformation_tuple: "t" _L_BRACE (comp|searching) (_COMMA (comp|searching))* _R_BRACE
value_tuple: _L_BRACE val+ _R_BRACE

DATETIME.2: {datetime_fmt}
DATE.2: {date_fmt}
TIME.2: {time_fmt}
TRUE.1: {true_fmt}
FALSE.1: {false_fmt}
CONST.1: "empty()" | "null" | "null()" | "NULL"
FLOAT.1: /-?\d+\.\d+([eE][-+]?\d+)?/
INT.1: /-?\d+/

val: prop
    | transformation_tuple
    | value_tuple
    | TRUE
    | FALSE
    | CONST
    | DATETIME
    | DATE
    | TIME
    | FLOAT
    | INT
    | QUOTED_VAL
    | UNQUOTED_VAL
"""

# ---- Filter Section ----
FILTERS = rf"""
filter: expr_term

expr_term: comp
         | listing
         | searching
         | logical
         | _L_BRACE expr_term _R_BRACE

comp: comp_term _L_BRACE prop _COMMA val _R_BRACE
    | prop _EQUALITY comp_term _EQUALITY val
    | prop _EQUALITY val

listing: list_term _L_BRACE prop _COMMA _L_BRACE val (_COMMA val)* _R_BRACE _R_BRACE
searching: search_term _L_BRACE prop _COMMA val _R_BRACE

logical: and_ | or_ | not_
and_: "and" _L_BRACE expr_term (_COMMA expr_term)+ _R_BRACE
or_: "or" _L_BRACE expr_term (_COMMA expr_term)+ _R_BRACE
not_: "not" _L_BRACE expr_term _R_BRACE

!comp_term: "{EQ}" | "{NE}" | "{GT}" | "{GE}" | "{LT}" | "{LE}"
!list_term: "{IN}"
!search_term: "like" | "ilike"
!logical_term: "{AND}" | "{OR}" | "{NOT}"

_filter_terms: comp_term | logical_term | list_term | search_term
"""

# ---- Transformation Section ----
TRANSFORMATIONS = r"""
transformation: transformation_funcs
transformation_funcs: sort | select | distinct

sort: "sort" _signed_props
distinct: "distinct" _L_BRACE prop? (_COMMA prop)* _R_BRACE


_signed_props: _L_BRACE _R_BRACE
             | _L_BRACE sign_prop (_COMMA sign_prop)* _R_BRACE
!sign_prop: ["+"|"-"] prop



select: "select" _L_BRACE selection _R_BRACE
selection: selectable_field (_COMMA selectable_field)*
nested_selection: PROP_NO_DOT _L_BRACKET selectable_field (_COMMA selectable_field)* _R_BRACKET
selectable_field: PROP_NO_DOT
                | STAR
                | nested_selection



_transformation_prop_terms: "sort" | "select" | "distinct"
"""

# ---- Whitespace Handling ----
WHITESPACE = r"""
%ignore WS
WS: /[ \t\n]+/
"""

# ---- Final Grammar ----
FULL_GRAMMAR_TEMPLATE = START + CORE + LITERALS + FILTERS + TRANSFORMATIONS + PROP_RULES + WHITESPACE


def get_parser(
    time_fmt: str = TIME,
    true_fmt: str = TRUE,
    false_fmt: str = FALSE,
    date_fmt: str = DATE,
    datetime_fmt: str = DATETIME,
) -> Lark:
    grammar = FULL_GRAMMAR_TEMPLATE.format(
        true_fmt=true_fmt, false_fmt=false_fmt, time_fmt=time_fmt, date_fmt=date_fmt, datetime_fmt=datetime_fmt
    )
    return Lark(grammar, parser="lalr", start="start")
