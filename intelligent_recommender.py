import google.generativeai as genai
import json
import re
import os
from typing import Dict, List, Optional
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from dataclasses import dataclass
from dotenv import load_dotenv

@dataclass
class Recommender:
    id: str
    title: str
    description: str
    score: float
    impact: str
    category: str
    severity: str
    details: Dict
    potential_savings: Dict = None

load_dotenv()

class IntelligentRecommender:
    def __init__(self, api_key: str):
        self.api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=self.api_key)
        self.model('gemini-1.5-flash')
    
    def analyse_issues(self, json_data: Dict)->Dict:
        domain = json_data.get('DomainURL', 'unknown')
        device_type = json_data.get('DeviceType', 'unknown')
        