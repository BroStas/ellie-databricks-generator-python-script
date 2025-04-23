import streamlit as st
import json
import re
import requests
from typing import Dict, List, Any, Optional, Tuple

def parse_physical_model(json_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse the physical data model JSON and extract relevant information."""
    try:
        model = json_data.get('model', {})
        entities = model.get('entities', [])
        relationships = model.get('relationships', [])
        
        return {
            'entities': entities,
            'relationships': relationships,
            'model_name': model.get('name', 'Unnamed Model')
        }
    except Exception as e:
        st.error(f"Error parsing JSON: {str(e)}")
        return {'entities': [], 'relationships': [], 'model_name': 'Error Model'}

def sanitize_identifier(name: str, sanitize_method: str = "underscore") -> str:
    """
    Sanitize SQL identifiers (table names, column names) to handle spaces and special characters.
    
    Parameters:
        name: The identifier to sanitize
        sanitize_method: Method to use for sanitization:
            - "underscore": Replace spaces and special chars with underscores (Databricks-compatible)
            - "backtick": Quote with backticks (may cause issues with Databricks)
    
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
    else:  # backtick
        return f"`{name}`"

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

def find_relationship_for_entity(entity_name: str, relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Find all relationships for a given entity."""
    entity_relationships = []
    
    for relationship in relationships:
        source = relationship.get('sourceEntity', {})
        target = relationship.get('targetEntity', {})
        
        source_name = source.get('name', '')
        target_name = target.get('name', '')
        
        if source_name == entity_name or target_name == entity_name:
            entity_relationships.append(relationship)
    
    return entity_relationships

def generate_ddl(model_data: Dict[str, Any], include_options: Dict[str, bool]) -> str:
    """Generate DDL statements for Databricks based on the physical model."""
    entities = model_data.get('entities', [])
    relationships = model_data.get('relationships', [])
    model_name = model_data.get('model_name', 'Unnamed Model')
    
    # Get the sanitization method from options
    sanitize_method = include_options.get('sanitize_method', 'underscore')
    
    ddl = [f"-- DDL for {model_name}"]
    ddl.append("-- Note: In Databricks, primary key and foreign key constraints are declarative and not enforced")
    
    # Add information block about Databricks constraints
    if include_options.get('include_constraint_info', True):
        ddl.append("""
-- Important information about Databricks constraints:
-- 1. Primary and foreign key constraints in Databricks are informational only and not enforced
-- 2. They serve as documentation for relationships between tables
-- 3. Databricks does not automatically validate that these constraints are satisfied
-- 4. You must implement data validation in your ETL processes to maintain data integrity
-- For more information, see: https://docs.databricks.com/en/tables/constraints.html
        """)
    
    # Generate CREATE DATABASE if selected
    if include_options.get('create_database', True):
        # Create a safe database name (remove special chars and spaces)
        safe_db_name = re.sub(r'[^a-zA-Z0-9_]', '_', model_name.lower())
        ddl.append(f"CREATE DATABASE IF NOT EXISTS {safe_db_name};")
        ddl.append(f"USE {safe_db_name};")
    
    # Generate CREATE TABLE statements (without constraints)
    for entity in entities:
        entity_name = entity.get('name', '')
        attributes = entity.get('attributes', [])
        
        if not entity_name or not attributes:
            continue
        
        # Sanitize table name to handle spaces
        sanitized_entity_name = sanitize_identifier(entity_name, sanitize_method)
        
        # Start CREATE TABLE statement
        table_stmt = f"CREATE TABLE IF NOT EXISTS {sanitized_entity_name} (\n"
        
        # Add columns
        columns = []
        
        for attr in attributes:
            attr_name = attr.get('name', '')
            metadata = attr.get('metadata', {})
            data_type = map_datatype_to_databricks(metadata.get('Data type', 'STRING'))
            not_null = metadata.get('Not null', False)
            description = metadata.get('description', '')
            
            # Sanitize column name to handle spaces
            sanitized_attr_name = sanitize_identifier(attr_name, sanitize_method)
            
            column_def = f"  {sanitized_attr_name} {data_type}"
            
            if not_null:
                column_def += " NOT NULL"
                
            # Add a comment if available
            if description and include_options.get('include_comments', True):
                # Escape single quotes in description
                escaped_description = description.replace("'", "''")
                column_def += f" COMMENT '{escaped_description}'"
                
            columns.append(column_def)
        
        # Add table columns
        table_stmt += ",\n".join(columns)
        
        # Add table options
        table_stmt += "\n)"
        
        # Add clustering if selected
        if include_options.get('add_clustering', False):
            # Find primary keys for clustering
            primary_keys = []
            for attr in attributes:
                if attr.get('metadata', {}).get('PK', False):
                    sanitized_attr_name = sanitize_identifier(attr.get('name', ''), sanitize_method)
                    if sanitized_attr_name:
                        primary_keys.append(sanitized_attr_name)
                        
            if primary_keys:
                table_stmt += f"\nCLUSTERED BY ({primary_keys[0]})"
        
        # Add table comment if available
        entity_description = entity.get('metadata', {}).get('Description', '')
        if entity_description and include_options.get('include_comments', True):
            # Escape single quotes in description
            escaped_entity_description = entity_description.replace("'", "''")
            table_stmt += f"\nCOMMENT '{escaped_entity_description}'"
        
        # Add Delta format specification
        if include_options.get('use_delta', True):
            table_stmt += f"\nUSING DELTA"
        
        table_stmt += ";"
        ddl.append(table_stmt)
    
    # Add primary key constraints using ALTER TABLE statements
    if include_options.get('include_pk', True):
        ddl.append("\n-- Adding Primary Key Constraints (Informational, not enforced)")
        for entity in entities:
            entity_name = entity.get('name', '')
            attributes = entity.get('attributes', [])
            
            if not entity_name or not attributes:
                continue
                
            # Sanitize table name
            sanitized_entity_name = sanitize_identifier(entity_name, sanitize_method)
            
            # Find primary keys
            primary_keys = []
            for attr in attributes:
                if attr.get('metadata', {}).get('PK', False):
                    sanitized_attr_name = sanitize_identifier(attr.get('name', ''), sanitize_method)
                    if sanitized_attr_name:
                        primary_keys.append(sanitized_attr_name)
            
            if primary_keys:
                # Create constraint name
                safe_entity_name = re.sub(r'[^a-zA-Z0-9_]', '_', entity_name.lower())
                pk_name = f"pk_{safe_entity_name}"
                
                # Add ALTER TABLE statement for primary key
                pk_cols = ', '.join(primary_keys)
                alter_stmt = f"ALTER TABLE {sanitized_entity_name} ADD CONSTRAINT {pk_name} " \
                           f"PRIMARY KEY ({pk_cols});"
                ddl.append(alter_stmt)
    
    # Add foreign key constraints using ALTER TABLE
    if include_options.get('include_foreign_keys', True):
        ddl.append("\n-- Adding Foreign Key Constraints (Informational, not enforced)")
        
        # Track added foreign key constraints to avoid duplicates
        added_fk_constraints = set()
        
        for relationship in relationships:
            source = relationship.get('sourceEntity', {})
            target = relationship.get('targetEntity', {})
            
            source_name = source.get('name', '')
            target_name = target.get('name', '')
            source_attrs = source.get('attributeNames', [])
            target_attrs = target.get('attributeNames', [])
            
            if not (source_name and target_name and source_attrs and target_attrs):
                continue
            
            # Sanitize names to handle spaces
            sanitized_source_name = sanitize_identifier(source_name, sanitize_method)
            sanitized_target_name = sanitize_identifier(target_name, sanitize_method)
            sanitized_source_attrs = [sanitize_identifier(attr, sanitize_method) for attr in source_attrs]
            sanitized_target_attrs = [sanitize_identifier(attr, sanitize_method) for attr in target_attrs]
            
            # Create a safe constraint name (no spaces or special chars)
            safe_source_name = re.sub(r'[^a-zA-Z0-9_]', '_', source_name.lower())
            safe_target_name = re.sub(r'[^a-zA-Z0-9_]', '_', target_name.lower())
            fk_name = f"fk_{safe_target_name}_{safe_source_name}"
            
            # Create a unique identifier for this constraint to avoid duplicates
            constraint_key = f"{sanitized_target_name}_{','.join(sanitized_target_attrs)}_{sanitized_source_name}_{','.join(sanitized_source_attrs)}"
            
            # Skip if this constraint has already been added
            if constraint_key in added_fk_constraints:
                continue
                
            added_fk_constraints.add(constraint_key)
            
            alter_stmt = f"ALTER TABLE {sanitized_target_name} ADD CONSTRAINT {fk_name} " \
                        f"FOREIGN KEY ({', '.join(sanitized_target_attrs)}) " \
                        f"REFERENCES {sanitized_source_name}({', '.join(sanitized_source_attrs)});"
            
            ddl.append(alter_stmt)
    
    # Include foreign key constraints as comments if option is enabled
    elif include_options.get('include_fk_comments', True):
        ddl.append("\n-- Foreign Key Relationships (as comments)")
        
        # Track added foreign key comments to avoid duplicates
        added_fk_comments = set()
        
        for relationship in relationships:
            source = relationship.get('sourceEntity', {})
            target = relationship.get('targetEntity', {})
            
            source_name = source.get('name', '')
            target_name = target.get('name', '')
            source_attrs = source.get('attributeNames', [])
            target_attrs = target.get('attributeNames', [])
            
            if not (source_name and target_name and source_attrs and target_attrs):
                continue
                
            # Sanitize names for display in comments
            sanitized_source_name = sanitize_identifier(source_name, sanitize_method)
            sanitized_target_name = sanitize_identifier(target_name, sanitize_method)
            sanitized_source_attr = sanitize_identifier(source_attrs[0], sanitize_method) if source_attrs else ""
            sanitized_target_attr = sanitize_identifier(target_attrs[0], sanitize_method) if target_attrs else ""
            
            # Create a unique identifier for this comment to avoid duplicates
            comment_key = f"{sanitized_target_name}_{sanitized_target_attr}_{sanitized_source_name}_{sanitized_source_attr}"
            
            # Skip if this comment has already been added
            if comment_key in added_fk_comments:
                continue
                
            added_fk_comments.add(comment_key)
            
            fk_comment = f"-- Foreign Key Relationship: {sanitized_target_name}.{sanitized_target_attr} references {sanitized_source_name}.{sanitized_source_attr}"
            ddl.append(fk_comment)
    
    # Add validation examples if enabled
    if include_options.get('include_validation_examples', False):
        ddl.append("\n-- Example data validation queries for maintaining data integrity")
        ddl.append("-- These queries can help identify constraint violations that Databricks does not enforce")
        
        # Generate primary key validation examples
        for entity in entities:
            entity_name = entity.get('name', '')
            attributes = entity.get('attributes', [])
            primary_keys = []
            
            for attr in attributes:
                if attr.get('metadata', {}).get('PK', False):
                    sanitized_attr_name = sanitize_identifier(attr.get('name', ''), sanitize_method)
                    if sanitized_attr_name:
                        primary_keys.append(sanitized_attr_name)
            
            if primary_keys and entity_name:
                sanitized_entity_name = sanitize_identifier(entity_name, sanitize_method)
                pk_cols = ', '.join(primary_keys)
                
                ddl.append(f"""
-- Validate primary key uniqueness in {sanitized_entity_name}
SELECT {pk_cols}, COUNT(*) as count
FROM {sanitized_entity_name}
GROUP BY {pk_cols}
HAVING COUNT(*) > 1;
                """)
        
        # Generate foreign key validation examples
        # Track added validation examples to avoid duplicates
        added_validations = set()
        
        for relationship in relationships:
            source = relationship.get('sourceEntity', {})
            target = relationship.get('targetEntity', {})
            
            source_name = source.get('name', '')
            target_name = target.get('name', '')
            source_attrs = source.get('attributeNames', [])
            target_attrs = target.get('attributeNames', [])
            
            if not (source_name and target_name and source_attrs and target_attrs):
                continue
                
            sanitized_source_name = sanitize_identifier(source_name, sanitize_method)
            sanitized_target_name = sanitize_identifier(target_name, sanitize_method)
            sanitized_source_attrs = [sanitize_identifier(attr, sanitize_method) for attr in source_attrs]
            sanitized_target_attrs = [sanitize_identifier(attr, sanitize_method) for attr in target_attrs]
            
            if len(sanitized_source_attrs) == 1 and len(sanitized_target_attrs) == 1:
                # Create a unique identifier for this validation to avoid duplicates
                validation_key = f"{sanitized_target_name}_{sanitized_target_attrs[0]}_{sanitized_source_name}_{sanitized_source_attrs[0]}"
                
                # Skip if this validation has already been added
                if validation_key in added_validations:
                    continue
                    
                added_validations.add(validation_key)
                
                ddl.append(f"""
-- Validate foreign key integrity between {sanitized_target_name} and {sanitized_source_name}
SELECT t.*
FROM {sanitized_target_name} t
LEFT JOIN {sanitized_source_name} s ON t.{sanitized_target_attrs[0]} = s.{sanitized_source_attrs[0]}
WHERE t.{sanitized_target_attrs[0]} IS NOT NULL
  AND s.{sanitized_source_attrs[0]} IS NULL;
                """)
    
    return "\n\n".join(ddl)

def show_databricks_info():
    """Show information about Databricks constraints support."""
    st.info("""
    **Databricks Constraints Support**
    
    In Databricks, primary key and foreign key constraints serve primarily as 
    informational constructs rather than enforced rules. This means:
    
    1. These constraints document relationships between tables
    2. They are NOT enforced by Databricks
    3. It's possible to insert data that violates these constraints
    4. They may be used for query optimization, but do not guarantee data integrity
    
    To maintain data integrity, implement validation in your ETL processes or use 
    Delta Live Tables (DLT) expectations.
    
    [Learn more in the Databricks documentation](https://docs.databricks.com/en/tables/constraints.html)
    """)

def load_sample_data() -> str:
    """Load sample data for the demo."""
    return '''
{
    "model": {
      "modelId": 173,
      "name": "Logistics Hub",
      "description": "Sample logistics database",
      "entities": [
        {
          "id": "91f0817a-bde6-11ef-858c-0242ac170004",
          "name": "Customer",
          "metadata": {
            "Description": "Customer information"
          },
          "attributes": [
            {
              "id": "91eff7aa-bde6-11ef-858c-0242ac170004",
              "name": "customer_id",
              "order": 0,
              "metadata": {
                "FK": false,
                "PK": true,
                "Unique": false,
                "Data type": "BIGINT",
                "description": "Unique customer identifier"
              }
            },
            {
              "id": "custom1",
              "name": "customer_name",
              "order": 1,
              "metadata": {
                "FK": false,
                "PK": false,
                "Not null": true,
                "Data type": "VARCHAR",
                "description": "Full customer name"
              }
            }
          ]
        },
        {
          "id": "91f0704a-bde6-11ef-858c-0242ac170004",
          "name": "Order",
          "metadata": {
            "Description": "Order information"
          },
          "attributes": [
            {
              "id": "91effd0e-bde6-11ef-858c-0242ac170004",
              "name": "order_id",
              "order": 0,
              "metadata": {
                "FK": false,
                "PK": true,
                "Not null": true,
                "Data type": "BIGINT",
                "description": "Unique order identifier"
              }
            },
            {
              "id": "91effe58-bde6-11ef-858c-0242ac170004",
              "name": "customer_id",
              "order": 1,
              "metadata": {
                "FK": true,
                "PK": false,
                "Not null": true,
                "Data type": "BIGINT",
                "description": "Reference to customer"
              }
            }
          ]
        }
      ],
      "relationships": [
        {
          "sourceEntity": {
            "id": "91f0817a-bde6-11ef-858c-0242ac170004",
            "name": "Customer",
            "startType": "one",
            "attributeNames": [
              "customer_id"
            ]
          },
          "targetEntity": {
            "id": "91f0704a-bde6-11ef-858c-0242ac170004",
            "name": "Order",
            "endType": "many",
            "attributeNames": [
              "customer_id"
            ]
          }
        }
      ]
    }
}
'''

def fetch_model_from_api(model_id: str, api_token: str, environment: str = "templates") -> str:
    """Fetch a physical data model from the Ellie.ai API.
    
    Args:
        model_id: The ID of the model to fetch
        api_token: API token for authentication
        environment: The environment slug (e.g., "templates", "app", etc.)
    """
    try:
        url = f"https://{environment}.ellie.ai/api/v1/models/{model_id}?token={api_token}"
        response = requests.get(url)
        
        if response.status_code == 200:
            return response.text
        else:
            error_msg = f"API request failed with status code {response.status_code}"
            if response.text:
                error_msg += f": {response.text}"
            raise Exception(error_msg)
    except Exception as e:
        raise Exception(f"Failed to fetch model: {str(e)}")

def main():
    st.set_page_config(
        page_title="Databricks DDL Generator",
        page_icon="🔮",
        layout="wide"
    )
    
    st.title("🔮 Databricks DDL Generator")
    st.markdown("Generate DDL statements for Databricks based on a physical data model JSON")
    
    # Create columns for layout
    col1, col2 = st.columns([2, 3])
    
    with col1:
        # Options
        st.subheader("DDL Options")
        
        options = {
            "create_database": st.checkbox("Create database", value=True, help="Generate CREATE DATABASE statement"),
            "include_pk": st.checkbox("Include primary keys", value=True, help="Include primary key constraints (informational only in Databricks)"),
            "use_delta": st.checkbox("Use Delta format", value=True, help="Specify Delta format for tables"),
        }
        
        # Constraint approach
        st.subheader("Constraint Approach")
        constraint_options = ["alter", "comments"]
        constraint_descriptions = {
            "alter": "Add constraints with ALTER TABLE statements",
            "comments": "Include relationships as comments only"
        }
        
        selected_constraint = st.radio(
            "How to include constraints:",
            constraint_options,
            index=0,
            format_func=lambda x: f"{x.title()} - {constraint_descriptions[x]}"
        )
        
        options["include_constraints_inline"] = False  # Always false now
        options["include_foreign_keys"] = selected_constraint == "alter"
        options["include_fk_comments"] = selected_constraint == "comments"
        
        # Display info about Databricks constraints
        show_databricks_info()
        
        # Add validation examples option
        options["include_validation_examples"] = st.checkbox(
            "Include validation queries", 
            value=False, 
            help="Include example SQL queries to validate data integrity"
        )
        
        # Include constraint documentation
        options["include_constraint_info"] = st.checkbox(
            "Include constraint documentation", 
            value=True, 
            help="Include comment block explaining Databricks constraint behavior"
        )
        
        # Simplified identifier sanitization - replace radio buttons with a checkbox
        use_underscore_sanitization = st.checkbox(
            "Replace spaces with underscores in table/column names", 
            value=True,
            help="Recommended for Databricks compatibility. If unchecked, names with spaces will be quoted."
        )
        
        # Set the sanitization method based on the checkbox
        options["sanitize_method"] = "underscore" if use_underscore_sanitization else "backtick"
        
        if not use_underscore_sanitization:
            st.warning("⚠️ Databricks Delta tables have limitations with special characters. Using underscores is recommended.")
        
        options["include_comments"] = st.checkbox("Include comments", value=True, help="Add comments for tables and columns")
        options["add_clustering"] = st.checkbox("Add clustering", value=False, help="Add CLUSTERED BY clause on primary key for performance")
        
        # Load sample button
        if st.button("Load Sample"):
            st.session_state.json_input = load_sample_data()
    
    # Initialize session state variables if they don't exist
    if 'json_input' not in st.session_state:
        st.session_state.json_input = ""
    
    with col2:
        # Add tabs for different input methods
        tab1, tab2 = st.tabs(["Direct JSON Input", "Fetch from Ellie.ai API"])
        
        with tab1:
            # JSON input area
            json_input = st.text_area(
                "Paste your physical data model JSON here:",
                value=st.session_state.json_input,
                height=300,
                key="json_text_area"
            )
            # Update the session state (this happens automatically via the key)
        
        with tab2:
            # API Fetch form
            st.subheader("Fetch from Ellie.ai API")
            
            col_id, col_token = st.columns(2)
            
            with col_id:
                model_id = st.text_input("Model ID", help="The numeric ID of your Ellie.ai model")
            
            with col_token:
                api_token = st.text_input("API Token", type="password", help="Your Ellie.ai API token")
            
            # Add environment selection
            environment = st.text_input("Environment", value="templates", 
                                       help="The Ellie.ai environment slug (e.g., 'templates', 'app', etc.)")
            
            fetch_button = st.button("Fetch Model")
            if fetch_button:
                if not model_id or not api_token:
                    st.error("Please provide both Model ID and API Token")
                else:
                    try:
                        with st.spinner("Fetching model data..."):
                            fetched_json = fetch_model_from_api(model_id, api_token, environment)
                            # Update the session state
                            st.session_state.json_input = fetched_json
                            st.success("Model fetched successfully! View and edit in the Direct JSON Input tab.")
                    except Exception as e:
                        st.error(f"Failed to fetch model: {str(e)}")
    
    # Get the JSON input from session state
    json_input = st.session_state.json_input
    
    if st.button("Generate DDL", type="primary"):
        if not json_input:
            st.error("Please provide a JSON input or fetch from API")
        else:
            try:
                # Parse JSON input
                json_data = json.loads(json_input)
                
                # Parse the physical model
                model_data = parse_physical_model(json_data)
                
                # Generate DDL
                ddl = generate_ddl(model_data, options)
                
                # Display DDL
                st.subheader("Generated DDL Statements")
                st.code(ddl, language="sql")
                
                # Add download button
                safe_filename = re.sub(r'[^a-zA-Z0-9_]', '_', model_data['model_name'].lower())
                st.download_button(
                    label="Download DDL",
                    data=ddl,
                    file_name=f"{safe_filename}_databricks_ddl.sql",
                    mime="text/plain"
                )
                
            except json.JSONDecodeError:
                st.error("Invalid JSON format. Please check your input.")
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main() 