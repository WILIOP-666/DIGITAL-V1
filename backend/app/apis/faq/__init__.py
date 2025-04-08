from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import datetime
import uuid
import databutton as db
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import openai

router = APIRouter()

# Helper function to sanitize storage keys
def sanitize_storage_key(key: str) -> str:
    """Sanitize storage key to only allow alphanumeric and ._- symbols"""
    return re.sub(r'[^a-zA-Z0-9._-]', '', key)

# Initialize OpenAI client
try:
    openai_api_key = db.secrets.get("OPENAI_API_KEY")
    openai_client = openai.OpenAI(api_key=openai_api_key)
except Exception as e:
    print(f"Error initializing OpenAI client: {e}")
    openai_client = None

# Data models
class FAQItem(BaseModel):
    id: str
    question: str
    answer: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    tags: List[str] = Field(default_factory=list)

class CreateFAQRequest(BaseModel):
    question: str
    answer: str
    tags: Optional[List[str]] = None

class UpdateFAQRequest(BaseModel):
    question: str
    answer: str
    tags: Optional[List[str]] = None

class FAQListResponse(BaseModel):
    faqs: List[FAQItem]

class FAQResponse(BaseModel):
    faq: FAQItem

class QueryRequest(BaseModel):
    question: str
    confidence_threshold: float = 0.5  # Default threshold for answers

class QueryResponse(BaseModel):
    answer: Optional[str] = None
    confidence: float = 0.0
    source_faq_id: Optional[str] = None
    has_answer: bool = False

# Vector search helper functions
class VectorSearch:
    def __init__(self):
        self.vectorizer = TfidfVectorizer()
        self.faqs = []
        self.vectors = None
        self.initialized = False
    
    def add_faqs(self, faqs):
        self.faqs = faqs
        if faqs:
            # Create corpus
            corpus = [f"{faq.question} {faq.answer}" for faq in faqs]
            self.vectors = self.vectorizer.fit_transform(corpus)
            self.initialized = True
        else:
            self.vectors = None
            self.initialized = False
    
    def search(self, query, threshold=0.5):
        if not self.initialized or not self.faqs:
            return None, 0.0
        
        query_vec = self.vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, self.vectors).flatten()
        
        # Find the best match
        best_idx = np.argmax(similarities)
        best_similarity = similarities[best_idx]
        
        if best_similarity >= threshold:
            return self.faqs[best_idx], float(best_similarity)
        
        return None, float(best_similarity)

# Initialize the vector search
vector_search = VectorSearch()

# Storage helper functions
def get_faqs() -> List[FAQItem]:
    """Get all FAQs from storage"""
    try:
        faqs_data = db.storage.json.get("faqs", default=[])
        faqs = [FAQItem(**faq) for faq in faqs_data]
        # Update vector search with new FAQs
        vector_search.add_faqs(faqs)
        return faqs
    except Exception as e:
        print(f"Error getting FAQs: {e}")
        return []

def save_faqs(faqs: List[FAQItem]):
    """Save FAQs to storage and update vector search"""
    # Convert datetime objects to ISO format strings
    faqs_data = []
    for faq in faqs:
        faq_dict = faq.dict()
        # Convert datetime objects to strings
        faq_dict['created_at'] = faq.created_at.isoformat()
        faq_dict['updated_at'] = faq.updated_at.isoformat()
        faqs_data.append(faq_dict)
    
    db.storage.json.put(sanitize_storage_key("faqs"), faqs_data)
    # Update vector search with new FAQs
    vector_search.add_faqs(faqs)

# API endpoints for FAQs
@router.get("/", response_model=FAQListResponse)
def get_all_faqs():
    """Get all FAQ items"""
    faqs = get_faqs()
    return FAQListResponse(faqs=faqs)

@router.post("/", response_model=FAQResponse)
def create_faq(request: CreateFAQRequest):
    """Create a new FAQ item"""
    faqs = get_faqs()
    
    new_faq = FAQItem(
        id=str(uuid.uuid4()),
        question=request.question,
        answer=request.answer,
        tags=request.tags or [],
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now()
    )
    
    faqs.append(new_faq)
    save_faqs(faqs)
    
    return FAQResponse(faq=new_faq)

@router.get("/{faq_id}", response_model=FAQResponse)
def get_faq(faq_id: str):
    """Get a specific FAQ by ID"""
    faqs = get_faqs()
    faq = next((f for f in faqs if f.id == faq_id), None)
    
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    return FAQResponse(faq=faq)

@router.put("/{faq_id}", response_model=FAQResponse)
def update_faq(faq_id: str, request: UpdateFAQRequest):
    """Update an existing FAQ"""
    faqs = get_faqs()
    faq_index = next((i for i, f in enumerate(faqs) if f.id == faq_id), None)
    
    if faq_index is None:
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    updated_faq = FAQItem(
        id=faq_id,
        question=request.question,
        answer=request.answer,
        tags=request.tags or faqs[faq_index].tags,
        created_at=faqs[faq_index].created_at,
        updated_at=datetime.datetime.now()
    )
    
    faqs[faq_index] = updated_faq
    save_faqs(faqs)
    
    return FAQResponse(faq=updated_faq)

@router.delete("/{faq_id}")
def delete_faq(faq_id: str):
    """Delete an FAQ"""
    faqs = get_faqs()
    faq_index = next((i for i, f in enumerate(faqs) if f.id == faq_id), None)
    
    if faq_index is None:
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    faqs.pop(faq_index)
    save_faqs(faqs)
    
    return {"message": "FAQ deleted successfully"}

@router.post("/search", response_model=QueryResponse)
def search_faq(request: QueryRequest):
    """Search for an answer to a question"""
    # Make sure the vector search is initialized
    faqs = get_faqs()
    
    # If we have no FAQs, return no answer
    if not faqs:
        return QueryResponse(has_answer=False)
    
    # Perform the search
    best_match, confidence = vector_search.search(
        request.question, 
        threshold=request.confidence_threshold
    )
    
    if best_match:
        return QueryResponse(
            answer=best_match.answer,
            confidence=confidence,
            source_faq_id=best_match.id,
            has_answer=True
        )
    
    # If no direct match is found, try to use OpenAI if client is available
    if openai_client:
        try:
            # Format all FAQs as context
            faq_context = "\n\n".join([f"Question: {faq.question}\nAnswer: {faq.answer}" for faq in faqs])
            
            # Get response from OpenAI
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"You are a helpful assistant that answers questions based on the following FAQ information. If you don't find a match, reply with 'I don't have enough information to answer this question.' Here are the FAQs:\n\n{faq_context}"},
                    {"role": "user", "content": request.question}
                ]
            )
            
            ai_answer = response.choices[0].message.content
            
            # Check if the AI indicates it doesn't have information
            if "don't have enough information" in ai_answer.lower():
                return QueryResponse(has_answer=False, confidence=0.4)  # Lower confidence for AI fallback
            
            # Return AI-generated answer with moderate confidence
            return QueryResponse(
                answer=ai_answer,
                confidence=0.7,  # Moderate confidence for AI-generated answers
                has_answer=True
            )
            
        except Exception as e:
            print(f"Error using OpenAI for FAQ fallback: {e}")
            # Continue to the default no-answer response
    
    # If we get here, we have no answer
    return QueryResponse(has_answer=False, confidence=confidence)
