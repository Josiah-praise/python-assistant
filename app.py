import streamlit as st
from openai import OpenAI
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import time

# Load environment variables
load_dotenv()

# Configure OpenAI client for GitHub Models (Azure AI Inference)
client = OpenAI(
    base_url=os.getenv("API_BASE_URL", "https://models.inference.ai.azure.com"),
    api_key=os.getenv("GITHUB_TOKEN")
)

# Page config
st.set_page_config(
    page_title="Smart Code Assistant",
    page_icon="🤖",
    layout="wide"
)

# Initialize session state
if "conversations" not in st.session_state:
    st.session_state.conversations = {}
if "current_conversation" not in st.session_state:
    st.session_state.current_conversation = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_names" not in st.session_state:
    st.session_state.conversation_names = {}
if "is_first_message" not in st.session_state:
    st.session_state.is_first_message = True

def generate_chat_name(first_message):
    """Generate a meaningful name for the chat based on the first message"""
    try:
        response = client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "gpt-4o"),
            messages=[
                {
                    "role": "system", 
                    "content": "Generate a short, descriptive title (2-4 words) for this coding request. No quotes, just the title."
                },
                {"role": "user", "content": f"Coding request: {first_message}"}
            ],
            max_tokens=20,
            temperature=0.3
        )
        title = response.choices[0].message.content.strip()
        title = title.replace('"', '').replace("'", "")[:30]
        return title if title else "New Chat"
    except Exception:
        words = first_message.split()[:3]
        return " ".join(words).title()[:30] if words else "New Chat"

def generate_code(prompt, conversation_history):
    """Generate code using GitHub Models (Azure AI Inference) with conversation context"""
    
    system_message = {
        "role": "system",
        "content": """You are an expert Python developer. Generate clean, well-commented, production-ready code.

Guidelines:
- Provide working, executable code
- Include proper error handling
- Add clear comments explaining key parts
- Use modern Python practices
- If the request is unclear, ask clarifying questions
- Format code with proper indentation

Always respond with code and a brief explanation of what it does."""
    }
    
    messages = [system_message]
    
    # Add conversation history (last 8 messages)
    if conversation_history:
        messages.extend(conversation_history[-8:])
    
    # Add current user prompt
    messages.append({"role": "user", "content": prompt})
    
    try:
        response = client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "gpt-4o"),
            messages=messages,
            max_tokens=1500,
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        error_msg = str(e)
        if "rate limit" in error_msg.lower():
            return "⚠️ Rate limit reached. Please wait a moment before trying again. The free GitHub Models tier has usage limits."
        elif "quota" in error_msg.lower():
            return "⚠️ Quota exceeded. You may need to wait for the quota to reset or check your GitHub Models usage."
        else:
            return f"Error generating code: {error_msg}"


def save_conversation(conversation_id, messages, name=None):
    """Save conversation to file"""
    try:
        if not os.path.exists("conversations"):
            os.makedirs("conversations")
        
        # Create a safe filename
        safe_filename = conversation_id.replace("/", "_").replace("\\", "_")
        filepath = f"conversations/{safe_filename}.json"
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "id": conversation_id,
                "name": name or conversation_id,
                "created": datetime.now().isoformat(),
                "messages": messages
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        st.error(f"Error saving conversation: {str(e)}")

def load_conversation(conversation_id):
    """Load conversation from file"""
    try:
        safe_filename = conversation_id.replace("/", "_").replace("\\", "_")
        filepath = f"conversations/{safe_filename}.json"
        
        if not os.path.exists(filepath):
            return [], None
            
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("messages", []), data.get("name", conversation_id)
    except Exception as e:
        st.error(f"Error loading conversation: {str(e)}")
        return [], None

def main():
    st.title("🤖 Smart Code Assistant")
    st.markdown("Describe what you want to build, and I'll generate the code for you!")
    
    # Sidebar for conversation management
    with st.sidebar:
        st.header("Conversations")
        
        # New conversation button
        if st.button("➕ New Conversation"):
            new_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            st.session_state.current_conversation = new_id
            st.session_state.messages = []
            st.session_state.conversation_names[new_id] = "New Chat"
            st.session_state.is_first_message = True
            # Save empty conversation file
            save_conversation(new_id, [], "New Chat")
            st.rerun()
        
        # Current conversation name editor
        if st.session_state.current_conversation:
            current_name = st.session_state.conversation_names.get(
                st.session_state.current_conversation, 
                st.session_state.current_conversation
            )
            
            new_name = st.text_input(
                "Chat Name:", 
                value=current_name,
                key="chat_name_input"
            )
            
            if new_name != current_name:
                st.session_state.conversation_names[st.session_state.current_conversation] = new_name
                save_conversation(
                    st.session_state.current_conversation, 
                    st.session_state.messages, 
                    new_name
                )
        
        # List existing conversations with better handling
        conv_files = []
        if os.path.exists("conversations"):
            conv_files = [f.replace(".json", "") for f in os.listdir("conversations") if f.endswith(".json")]
            conv_files.sort(reverse=True)  # Most recent first
        
        # Load conversation names from files
        conv_display_names = {}
        for conv_id in conv_files:
            _, name = load_conversation(conv_id)
            conv_display_names[conv_id] = name or conv_id
            st.session_state.conversation_names[conv_id] = name or conv_id
        
        if conv_files:
            selected_conv = st.selectbox(
                "Switch to Conversation:",
                [""] + conv_files,  # Empty option to avoid auto-switching
                format_func=lambda x: "Select conversation..." if x == "" else conv_display_names.get(x, x),
                key="conversation_selector"
            )
            
            if selected_conv and selected_conv != st.session_state.current_conversation:
                # Save current conversation before switching
                if st.session_state.messages and st.session_state.current_conversation:
                    current_name = st.session_state.conversation_names.get(
                        st.session_state.current_conversation,
                        st.session_state.current_conversation
                    )
                    save_conversation(st.session_state.current_conversation, st.session_state.messages, current_name)
                
                # Load new conversation
                st.session_state.current_conversation = selected_conv
                messages, name = load_conversation(selected_conv)
                st.session_state.messages = messages
                st.session_state.conversation_names[selected_conv] = name or selected_conv
                st.session_state.is_first_message = len(messages) == 0
                st.rerun()
        
        st.markdown("---")
        st.markdown("### Tips:")
        st.markdown("- Be specific about what you want")
        st.markdown("- Ask for modifications to previous code")
        st.markdown("- Request error handling, tests, or documentation")
        st.markdown("- **Note**: Using GitHub Models free tier with rate limits")
        
        # Add rate limit info
        st.markdown("---")
        st.markdown("**Rate Limits:**")
        st.markdown("- 15 requests per minute")
        st.markdown("- 150 requests per day")
        st.markdown("- If you hit limits, wait a moment and try again")
    
    # Main chat interface
    # Display conversation history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                # Split response into explanation and code if possible
                content = message["content"]
                if "```" in content:
                    parts = content.split("```")
                    for i, part in enumerate(parts):
                        if i % 2 == 0:  # Text parts
                            if part.strip():
                                st.markdown(part)
                        else:  # Code parts
                            # Try to detect language
                            lines = part.split('\n')
                            if lines[0].strip() in ['python', 'py', 'javascript', 'js', 'html', 'css', 'sql']:
                                lang = lines[0].strip()
                                code = '\n'.join(lines[1:])
                            else:
                                lang = 'python'  # Default
                                code = part
                            st.code(code, language=lang)
                else:
                    st.markdown(content)
            else:
                st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Describe the code you want me to generate..."):
        # Create new conversation if none exists
        if not st.session_state.current_conversation:
            new_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            st.session_state.current_conversation = new_id
            st.session_state.messages = []
            st.session_state.is_first_message = True
        
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Generate chat name if this is the first message
        if st.session_state.is_first_message:
            with st.spinner("Generating chat name..."):
                chat_name = generate_chat_name(prompt)
                st.session_state.conversation_names[st.session_state.current_conversation] = chat_name
                st.session_state.is_first_message = False
        
        # Generate and display assistant response
        with st.chat_message("assistant"):
            with st.spinner("Generating code..."):
                response = generate_code(prompt, st.session_state.messages[:-1])
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                # Display the response with proper formatting
                if "```" in response:
                    parts = response.split("```")
                    for i, part in enumerate(parts):
                        if i % 2 == 0:  # Text parts
                            if part.strip():
                                st.markdown(part)
                        else:  # Code parts
                            lines = part.split('\n')
                            if lines[0].strip() in ['python', 'py', 'javascript', 'js', 'html', 'css', 'sql']:
                                lang = lines[0].strip()
                                code = '\n'.join(lines[1:])
                            else:
                                lang = 'python'
                                code = part
                            st.code(code, language=lang)
                else:
                    st.markdown(response)
        
        # Save conversation with name
        current_name = st.session_state.conversation_names.get(
            st.session_state.current_conversation,
            st.session_state.current_conversation
        )
        save_conversation(st.session_state.current_conversation, st.session_state.messages, current_name)
        st.rerun()

if __name__ == "__main__":
    # Check if GitHub token is set
    if not os.getenv("GITHUB_TOKEN"):
        st.error("Please set your GITHUB_TOKEN in the .env file")
        st.markdown("""
        **To get your GitHub token:**
        1. Go to https://github.com/settings/tokens
        2. Click "Generate new token (classic)"
        3. Give it a name like "Azure AI Models"
        4. Select scopes: `repo` and `read:user`
        5. Copy the token and add it to your .env file
        """)
        st.stop()
    
    main()