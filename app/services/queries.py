import yaml

def load_queries(yaml_path="queries_registry.yml"):
    """Load all queries from the YAML registry."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data
