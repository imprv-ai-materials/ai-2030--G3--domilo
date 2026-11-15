{#- Kombinacja kolumn jest kluczem modelu: zwraca powtórzone kombinacje. -#}
{% test unikalna_kombinacja(model, kolumny) %}
select {{ kolumny | join(', ') }}, count(*) as liczba
from {{ model }}
group by {{ kolumny | join(', ') }}
having count(*) > 1
{% endtest %}
