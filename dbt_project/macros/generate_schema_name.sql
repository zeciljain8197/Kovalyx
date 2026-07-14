{#
    dbt's default generate_schema_name concatenates the profile's base
    schema with any model-level +schema config (e.g. "staging" + "marts"
    -> "staging_marts"), which silently produced staging_marts/
    staging_staging instead of the intended marts/staging schemas —
    supabase_schema.sql's RLS setup and every downstream consumer
    (frontend, Streamlit monitor) query marts.*/staging.* directly.
    This is dbt's own documented override to use the custom schema name
    as-is instead of concatenating.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
