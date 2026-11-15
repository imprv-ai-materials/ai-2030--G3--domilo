{#- Wartości kolumny w zakresie [min, max] (granice włącznie; NULL pomijamy, od tego jest not_null).
    Zwraca wiersze poza zakresem, więc test przechodzi, gdy wynik jest pusty. -#}
{% test zakres(model, column_name, min=none, max=none) %}
select *
from {{ model }}
where {{ column_name }} is not null
  and (
      {% if min is not none %}{{ column_name }} < {{ min }}{% else %}false{% endif %}
      or {% if max is not none %}{{ column_name }} > {{ max }}{% else %}false{% endif %}
  )
{% endtest %}
