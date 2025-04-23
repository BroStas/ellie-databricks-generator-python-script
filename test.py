import json
import re
from typing import Dict, List, Any

def sanitize_identifier(name: str, sanitize_method: str = "underscore") -> str:
    """
    Sanitize SQL identifiers (table names, column names) to handle spaces and special characters.
    
    Parameters:
        name: The identifier to sanitize
        sanitize_method: Method to use for sanitization:
            - "underscore": Replace spaces and special chars with underscores (Databricks-compatible)
            - "backtick": Quote with backticks (standard SQL but can cause issues with Databricks)
            - "double_quote": Quote with double quotes (standard SQL but can cause issues with Databricks)
    
    Returns:
        Sanitized identifier
    """
    if not name:
        return name
    
    # Remove any existing quotes if they exist
    name = name.strip('`"')
    
    if sanitize_method == "underscore":
        # Replace spaces and special characters with underscore
        # Keep alphanumeric and underscore characters
        return re.sub(r'[^a-zA-Z0-9_]', '_', name)
    elif sanitize_method == "backtick":
        return f"`{name}`"
    else:  # double quotes
        return f'"{name}"'

def map_datatype_to_databricks(data_type: str) -> str:
    """Map the data type from the model to Databricks supported types."""
    data_type = data_type.upper()
    
    # Mapping of data types
    type_mapping = {
        'VARCHAR': 'STRING',
        'VARCHAR(255)': 'STRING',
        'CHAR': 'STRING',
        'TEXT': 'STRING',
        'FLOAT': 'DOUBLE',
        'DOUBLE PRECISION': 'DOUBLE',
        'INTEGER': 'INT',
        'SMALLINT': 'SMALLINT',
        'TIMESTAMP': 'TIMESTAMP',
        'TIMESTAMP_TZ': 'TIMESTAMP',
        'DATE': 'DATE',
        'BOOLEAN': 'BOOLEAN',
        'DECIMAL': 'DECIMAL',
        'NUMBER': 'DECIMAL',
        'BIGINT': 'BIGINT',
        'TINYINT': 'TINYINT'
    }
    
    # Try exact match first
    if data_type in type_mapping:
        return type_mapping[data_type]
    
    # Handle VARCHAR with length specification
    if data_type.startswith('VARCHAR(') or data_type.startswith('CHAR('):
        return 'STRING'
    
    return data_type

def generate_test_ddl(entity: Dict[str, Any], sanitize_method: str) -> str:
    """Generate a sample DDL for testing purposes"""
    entity_name = entity.get('name', '')
    attributes = entity.get('attributes', [])
    
    if not entity_name or not attributes:
        return ""
    
    # Sanitize table name to handle spaces
    sanitized_entity_name = sanitize_identifier(entity_name, sanitize_method)
    
    # Start CREATE TABLE statement
    table_stmt = f"CREATE TABLE IF NOT EXISTS {sanitized_entity_name} (\n"
    
    # Add columns
    columns = []
    primary_keys = []
    
    for attr in attributes:
        attr_name = attr.get('name', '')
        metadata = attr.get('metadata', {})
        data_type = map_datatype_to_databricks(metadata.get('Data type', 'STRING'))
        is_pk = metadata.get('PK', False)
        not_null = metadata.get('Not null', False)
        description = metadata.get('description', '')
        
        # Sanitize column name to handle spaces
        sanitized_attr_name = sanitize_identifier(attr_name, sanitize_method)
        
        column_def = f"  {sanitized_attr_name} {data_type}"
        
        if not_null:
            column_def += " NOT NULL"
            
        # Add a comment if available
        if description:
            # Escape single quotes in description
            escaped_description = description.replace("'", "''")
            column_def += f" COMMENT '{escaped_description}'"
            
        columns.append(column_def)
        
        if is_pk:
            primary_keys.append(sanitized_attr_name)
    
    table_stmt += ",\n".join(columns)
    
    # Add primary key constraint if exists
    if primary_keys:
        table_stmt += f",\n  PRIMARY KEY ({', '.join(primary_keys)})"
    
    # Add table options
    table_stmt += "\n)"
    
    # Add Delta format specification
    table_stmt += f"\nUSING DELTA;"
    
    return table_stmt

test_data = '''
{
  "model": {
    "modelId": 27679,
    "name": "Customers and sales orders - physical (SQL Ready)",
    "description": "",
    "entities": [
      {
        "id": "e1c924bb-7e67-4f4d-a313-64489659e314",
        "name": "Address",
        "metadata": {
          "Description": "Customer address information"
        },
        "attributes": [
          {
            "id": "b1f11a5a-a70e-11ef-83d9-0242ac120002",
            "name": "Address ID",
            "order": 0,
            "metadata": {
              "FK": false,
              "PK": true,
              "Unique": true,
              "Not null": true,
              "Data type": "INT",
              "description": "Primary address identifier"
            }
          },
          {
            "id": "b1f11de8-a70e-11ef-83d9-0242ac120002",
            "name": "Street name",
            "order": 1,
            "metadata": {
              "FK": false,
              "PK": false,
              "Not null": false,
              "Data type": "VARCHAR(255)",
              "description": "Name of the street"
            }
          }
        ]
      }
    ],
    "relationships": []
  }
}
'''

def test_underscore_sanitization():
    """Test the underscore sanitization method for Databricks compatibility"""
    json_data = json.loads(test_data)
    entity = json_data["model"]["entities"][0]
    
    # Test with underscore sanitization
    ddl = generate_test_ddl(entity, "underscore")
    
    # Print the results with underscore sanitization
    print("=== DDL with UNDERSCORE Sanitization ===")
    print(ddl)
    print("\n")
    
    # Make sure the Address ID was converted to Address_ID
    assert "Address_ID" in ddl, "Address ID was not properly converted to Address_ID"
    assert "Street_name" in ddl, "Street name was not properly converted to Street_name"
    
    return ddl

def test_quote_sanitization():
    """Test the backtick sanitization method (which may cause errors in Databricks)"""
    json_data = json.loads(test_data)
    entity = json_data["model"]["entities"][0]
    
    # Test with backtick sanitization
    ddl = generate_test_ddl(entity, "backtick")
    
    # Print the results with backtick sanitization
    print("=== DDL with BACKTICK Sanitization ===")
    print(ddl)
    print("\n")
    
    # Make sure the Address ID was converted to `Address ID`
    assert "`Address ID`" in ddl, "Address ID was not properly converted to `Address ID`"
    assert "`Street name`" in ddl, "Street name was not properly converted to `Street name`"
    
    return ddl

if __name__ == "__main__":
    print("Testing different sanitization methods for Databricks compatibility\n")
    
    # Run the tests
    underscore_ddl = test_underscore_sanitization()
    backtick_ddl = test_quote_sanitization()
    
    print("Tests completed. The underscore sanitization method should be compatible with Databricks.") 