from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import databutton as db
from datetime import datetime, timedelta
import uuid
import openai
import re

router = APIRouter()

# Models
class Customer(BaseModel):
    id: str
    name: str
    email: str
    created_at: datetime

class Message(BaseModel):
    id: str
    conversation_id: str
    content: str
    sender_type: str  # 'customer', 'merchant', 'ai'
    timestamp: datetime
    status: str = "sent"  # 'sent', 'delivered', 'read', 'failed'
    is_reviewed: bool = False  # Whether a merchant has reviewed an AI message

class Conversation(BaseModel):
    id: str
    customer_id: str
    title: str
    last_message_time: datetime
    created_at: datetime
    is_active: bool = True

class ConversationWithDetails(Conversation):
    customer: Customer
    messages: List[Message]

class ConversationListResponse(BaseModel):
    conversations: List[Conversation]

class ConversationDetailResponse(BaseModel):
    conversation: ConversationWithDetails

class MessageResponse(BaseModel):
    message: Message

class CreateMessageRequest(BaseModel):
    content: str
    sender_type: str

class CreateConversationRequest(BaseModel):
    customer_id: str
    title: str
    initial_message: Optional[str] = None

class AIResponseRequest(BaseModel):
    conversation_id: str
    customer_message_id: str

# Helper functions
def sanitize_storage_key(key: str) -> str:
    """Sanitize storage key to only allow alphanumeric and ._- symbols"""
    return re.sub(r'[^a-zA-Z0-9._-]', '', key)

# Storage utility functions
def get_customers():
    try:
        return db.storage.json.get("chat_customers", default=[])
    except:
        return []

def save_customers(customers):
    db.storage.json.put(sanitize_storage_key("chat_customers"), customers)

def get_conversations():
    try:
        return db.storage.json.get("chat_conversations", default=[])
    except:
        return []

def save_conversations(conversations):
    db.storage.json.put(sanitize_storage_key("chat_conversations"), conversations)

def get_messages():
    try:
        return db.storage.json.get("chat_messages", default=[])
    except:
        return []

def save_messages(messages):
    db.storage.json.put(sanitize_storage_key("chat_messages"), messages)

# Helper to find customer by ID
def find_customer(customer_id):
    customers = get_customers()
    for customer in customers:
        if customer["id"] == customer_id:
            return customer
    return None

# API Endpoints for conversations
@router.get("/conversations", response_model=ConversationListResponse)
def get_all_conversations():
    conversations = get_conversations()
    
    # Handle datetimes for sorting
    for conv in conversations:
        if isinstance(conv["last_message_time"], str):
            conv["last_message_time"] = datetime.fromisoformat(conv["last_message_time"])
        if isinstance(conv["created_at"], str):
            conv["created_at"] = datetime.fromisoformat(conv["created_at"])
    
    # Sort by last message time, most recent first
    conversations.sort(key=lambda x: x["last_message_time"], reverse=True)
    
    # Convert back to strings for JSON serialization
    for conv in conversations:
        conv["last_message_time"] = conv["last_message_time"].isoformat()
        conv["created_at"] = conv["created_at"].isoformat()
    
    return ConversationListResponse(conversations=conversations)

@router.post("/conversations", response_model=ConversationDetailResponse)
def create_conversation(request: CreateConversationRequest):
    customer = find_customer(request.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    conversations = get_conversations()
    messages = get_messages()
    
    now = datetime.now()
    conversation_id = str(uuid.uuid4())
    
    new_conversation = {
        "id": conversation_id,
        "customer_id": request.customer_id,
        "title": request.title,
        "last_message_time": now.isoformat(),
        "created_at": now.isoformat(),
        "is_active": True
    }
    
    conversations.append(new_conversation)
    
    # Add initial message if provided
    conversation_messages = []
    if request.initial_message:
        message_id = str(uuid.uuid4())
        new_message = {
            "id": message_id,
            "conversation_id": conversation_id,
            "content": request.initial_message,
            "sender_type": "customer",
            "timestamp": now.isoformat(),
            "status": "sent",
            "is_reviewed": False
        }
        messages.append(new_message)
        conversation_messages.append(new_message)
    
    save_conversations(conversations)
    save_messages(messages)
    
    return ConversationDetailResponse(
        conversation={
            **new_conversation,
            "customer": customer,
            "messages": conversation_messages
        }
    )

@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(conversation_id: str):
    conversations = get_conversations()
    messages = get_messages()
    
    # Find the conversation
    conversation = None
    for conv in conversations:
        if conv["id"] == conversation_id:
            conversation = conv
            break
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get customer details
    customer = find_customer(conversation["customer_id"])
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get messages for this conversation
    conversation_messages = [msg for msg in messages if msg["conversation_id"] == conversation_id]
    
    # Sort messages by timestamp
    for msg in conversation_messages:
        if isinstance(msg["timestamp"], str):
            msg["timestamp"] = datetime.fromisoformat(msg["timestamp"])
    
    conversation_messages.sort(key=lambda x: x["timestamp"])
    
    # Convert back to strings for JSON serialization
    for msg in conversation_messages:
        msg["timestamp"] = msg["timestamp"].isoformat()
    
    return ConversationDetailResponse(
        conversation={
            **conversation,
            "customer": customer,
            "messages": conversation_messages
        }
    )

@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
def add_message(conversation_id: str, request: CreateMessageRequest):
    conversations = get_conversations()
    messages = get_messages()
    
    # Find the conversation
    conversation_index = None
    for i, conv in enumerate(conversations):
        if conv["id"] == conversation_id:
            conversation_index = i
            break
    
    if conversation_index is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    now = datetime.now()
    message_id = str(uuid.uuid4())
    
    new_message = {
        "id": message_id,
        "conversation_id": conversation_id,
        "content": request.content,
        "sender_type": request.sender_type,
        "timestamp": now.isoformat(),
        "status": "sent",
        "is_reviewed": False if request.sender_type == "ai" else True
    }
    
    # Update the conversation's last message time
    conversations[conversation_index]["last_message_time"] = now.isoformat()
    
    messages.append(new_message)
    
    save_conversations(conversations)
    save_messages(messages)
    
    return MessageResponse(message=new_message)

@router.post("/conversations/{conversation_id}/generate-ai-response")
def generate_ai_response(conversation_id: str, request: AIResponseRequest):
    conversations = get_conversations()
    messages = get_messages()
    
    # Check if conversation exists
    conversation = None
    for conv in conversations:
        if conv["id"] == conversation_id:
            conversation = conv
            break
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get customer details
    customer = find_customer(conversation["customer_id"])
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get messages for this conversation
    conversation_messages = [msg for msg in messages if msg["conversation_id"] == conversation_id]
    for msg in conversation_messages:
        if isinstance(msg["timestamp"], str):
            msg["timestamp"] = datetime.fromisoformat(msg["timestamp"])
    
    conversation_messages.sort(key=lambda x: x["timestamp"])
    
    # Check if API key is available
    openai_api_key = db.secrets.get("OPENAI_API_KEY", None)
    if not openai_api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key not configured")
    
    # Format messages for OpenAI
    openai_messages = [
        {"role": "system", "content": "You are a helpful customer support agent for a digital products store. Be friendly, concise, and helpful."}
    ]
    
    # Add conversation history
    for msg in conversation_messages:
        role = "assistant" if msg["sender_type"] == "ai" else "user"
        openai_messages.append({"role": role, "content": msg["content"]})
    
    # Generate AI response
    try:
        openai_client = openai.OpenAI(api_key=openai_api_key)
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=openai_messages
        )
        
        ai_response = response.choices[0].message.content
        
        # Save the AI response as a new message
        now = datetime.now()
        message_id = str(uuid.uuid4())
        
        new_message = {
            "id": message_id,
            "conversation_id": conversation_id,
            "content": ai_response,
            "sender_type": "ai",
            "timestamp": now.isoformat(),
            "status": "sent",
            "is_reviewed": False
        }
        
        # Update conversation's last message time
        for i, conv in enumerate(conversations):
            if conv["id"] == conversation_id:
                conversations[i]["last_message_time"] = now.isoformat()
                break
        
        messages.append(new_message)
        
        save_conversations(conversations)
        save_messages(messages)
        
        return MessageResponse(message=new_message)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating AI response: {str(e)}")

@router.put("/messages/{message_id}/review")
def review_message(message_id: str):
    messages = get_messages()
    
    # Find and update the message
    for i, msg in enumerate(messages):
        if msg["id"] == message_id:
            if msg["sender_type"] != "ai":
                raise HTTPException(status_code=400, detail="Only AI messages can be reviewed")
            
            messages[i]["is_reviewed"] = True
            save_messages(messages)
            
            return {"message": "Message marked as reviewed"}
    
    raise HTTPException(status_code=404, detail="Message not found")

@router.put("/messages/{message_id}/edit")
def edit_message(message_id: str, request: CreateMessageRequest):
    messages = get_messages()
    
    # Find and update the message
    for i, msg in enumerate(messages):
        if msg["id"] == message_id:
            if msg["sender_type"] != "ai":
                raise HTTPException(status_code=400, detail="Only AI messages can be edited")
            
            messages[i]["content"] = request.content
            messages[i]["is_reviewed"] = True
            save_messages(messages)
            
            return MessageResponse(message=messages[i])
    
    raise HTTPException(status_code=404, detail="Message not found")

# API Endpoints for customers
@router.get("/customers")
def get_all_customers():
    customers = get_customers()
    return {"customers": customers}

@router.post("/customers")
def create_customer(customer: Customer):
    customers = get_customers()
    
    # Check if customer already exists
    for existing in customers:
        if existing["id"] == customer.id or existing["email"] == customer.email:
            raise HTTPException(status_code=400, detail="Customer already exists")
    
    new_customer = {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
        "created_at": customer.created_at.isoformat()
    }
    
    customers.append(new_customer)
    save_customers(customers)
    
    return {"customer": new_customer}

# For demo purposes, add some sample data if none exists
@router.post("/initialize-sample-data")
def initialize_sample_data():
    customers = get_customers()
    conversations = get_conversations()
    messages = get_messages()
    
    if customers and conversations and messages:
        return {"message": "Sample data already exists"}
    
    # Create sample customers
    sample_customers = [
        {
            "id": "cust1",
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "created_at": datetime.now().isoformat()
        },
        {
            "id": "cust2",
            "name": "Bob Smith",
            "email": "bob@example.com",
            "created_at": datetime.now().isoformat()
        },
        {
            "id": "cust3",
            "name": "Charlie Davis",
            "email": "charlie@example.com",
            "created_at": datetime.now().isoformat()
        }
    ]
    
    # Create sample conversations
    sample_conversations = [
        {
            "id": "conv1",
            "customer_id": "cust1",
            "title": "Help with download",
            "last_message_time": (datetime.now() - timedelta(hours=1)).isoformat(),
            "created_at": (datetime.now() - timedelta(days=1)).isoformat(),
            "is_active": True
        },
        {
            "id": "conv2",
            "customer_id": "cust2",
            "title": "Refund request",
            "last_message_time": (datetime.now() - timedelta(hours=3)).isoformat(),
            "created_at": (datetime.now() - timedelta(days=2)).isoformat(),
            "is_active": True
        },
        {
            "id": "conv3",
            "customer_id": "cust3",
            "title": "Product information",
            "last_message_time": (datetime.now() - timedelta(hours=5)).isoformat(),
            "created_at": (datetime.now() - timedelta(days=1, hours=12)).isoformat(),
            "is_active": True
        }
    ]
    
    # Create sample messages
    sample_messages = [
        # Conversation 1
        {
            "id": "msg1",
            "conversation_id": "conv1",
            "content": "Hi, I'm having trouble downloading the product I purchased. Can you help?",
            "sender_type": "customer",
            "timestamp": (datetime.now() - timedelta(hours=3)).isoformat(),
            "status": "read",
            "is_reviewed": True
        },
        {
            "id": "msg2",
            "conversation_id": "conv1",
            "content": "I'm sorry to hear you're having trouble. Could you please tell me which product you purchased and what error message you're seeing?",
            "sender_type": "ai",
            "timestamp": (datetime.now() - timedelta(hours=2, minutes=55)).isoformat(),
            "status": "read",
            "is_reviewed": True
        },
        {
            "id": "msg3",
            "conversation_id": "conv1",
            "content": "I bought the Premium eBook Bundle. When I click the download link, it says 'Access Denied'.",
            "sender_type": "customer",
            "timestamp": (datetime.now() - timedelta(hours=2, minutes=40)).isoformat(),
            "status": "read",
            "is_reviewed": True
        },
        {
            "id": "msg4",
            "conversation_id": "conv1",
            "content": "Thank you for the details. I'll reset your download link. Please check your email in the next 5 minutes for a new download link. If you continue to have issues, please let me know.",
            "sender_type": "ai",
            "timestamp": (datetime.now() - timedelta(hours=2, minutes=35)).isoformat(),
            "status": "read",
            "is_reviewed": False
        },
        {
            "id": "msg5",
            "conversation_id": "conv1",
            "content": "Thanks! I got the new link and was able to download successfully.",
            "sender_type": "customer",
            "timestamp": (datetime.now() - timedelta(hours=1)).isoformat(),
            "status": "read",
            "is_reviewed": True
        },
        
        # Conversation 2
        {
            "id": "msg6",
            "conversation_id": "conv2",
            "content": "Hello, I'd like to request a refund for my recent purchase. The product didn't meet my expectations.",
            "sender_type": "customer",
            "timestamp": (datetime.now() - timedelta(hours=5)).isoformat(),
            "status": "read",
            "is_reviewed": True
        },
        {
            "id": "msg7",
            "conversation_id": "conv2",
            "content": "I'm sorry to hear that. Could you please provide your order number and explain why the product didn't meet your expectations?",
            "sender_type": "ai",
            "timestamp": (datetime.now() - timedelta(hours=4, minutes=55)).isoformat(),
            "status": "read",
            "is_reviewed": True
        },
        {
            "id": "msg8",
            "conversation_id": "conv2",
            "content": "My order number is ORD-12345. I expected more advanced content, but the material was too basic for my needs.",
            "sender_type": "customer",
            "timestamp": (datetime.now() - timedelta(hours=4, minutes=30)).isoformat(),
            "status": "read",
            "is_reviewed": True
        },
        {
            "id": "msg9",
            "conversation_id": "conv2",
            "content": "I understand your concern. I'll process your refund right away. You should see the refund in your account within 3-5 business days.",
            "sender_type": "merchant",
            "timestamp": (datetime.now() - timedelta(hours=3)).isoformat(),
            "status": "read",
            "is_reviewed": True
        },
        
        # Conversation 3
        {
            "id": "msg10",
            "conversation_id": "conv3",
            "content": "Do you offer any discounts for bulk purchases of your digital products?",
            "sender_type": "customer",
            "timestamp": (datetime.now() - timedelta(hours=6)).isoformat(),
            "status": "read",
            "is_reviewed": True
        },
        {
            "id": "msg11",
            "conversation_id": "conv3",
            "content": "Yes, we do offer volume discounts! For purchases of 5+ licenses, we offer a 10% discount, and for 10+ licenses, we offer a 15% discount. Would you like me to provide more information about specific products?",
            "sender_type": "ai",
            "timestamp": (datetime.now() - timedelta(hours=5, minutes=55)).isoformat(),
            "status": "read",
            "is_reviewed": False
        }
    ]
    
    # Save sample data
    save_customers(sample_customers)
    save_conversations(sample_conversations)
    save_messages(sample_messages)
    
    return {"message": "Sample data initialized successfully"}
