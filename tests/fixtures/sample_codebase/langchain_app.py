"""Sample LangChain app with vector DB and RAG pipeline."""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains import LLMChain
import chromadb

llm = ChatOpenAI(model="gpt-4o")
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection("documents")

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant."),
    ("user", "{input}"),
])

chain = LLMChain(llm=llm, prompt=prompt)
