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

load_dotenv()

@dataclass
class LighthouseIssue:
    """Data class for lighthouse issues"""
    id: str
    title: str
    description: str
    score: float
    impact: str
    category: str
    severity: str
    details: Dict
    potential_savings: Dict = None

class LighthouseIssueAnalyzer:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable required")
        
        genai.configure(api_key=self.api_key)
        try:
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        except:
            self.model = genai.GenerativeModel('gemini-pro')
    
    def analyze_lighthouse_issues(self, lighthouse_json: Dict) -> Dict:
        """Extract and analyze all issues from Lighthouse report"""
        try:
            domain = lighthouse_json.get('DomainURL', 'unknown')
            device_type = lighthouse_json.get('deviceType', 'unknown')
            performance_score = lighthouse_json.get('PerformanceScore', 0)
            
            issues = self._extract_issues_with_poor_scores(lighthouse_json)
            
            if not issues:
                return {
                    "message": "No performance issues found (all scores >= 1.0)",
                    "website": domain,
                    "device_type": device_type,
                    "performance_score": performance_score
                }
            
            ai_analysis = self._analyze_issues_with_ai(issues, domain, device_type, performance_score)
            
            return {
                "website": domain,
                "device_type": device_type,
                "performance_score": performance_score,
                "total_issues_found": len(issues),
                "issues_summary": self._create_issues_summary(issues),
                "detailed_analysis": ai_analysis,
                "analysis_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Analysis failed: {str(e)}"}
    
    def _extract_issues_with_poor_scores(self, data: Dict) -> List[LighthouseIssue]:
        """Extract only issues with score < 1"""
        issues = []
        
        try:
            performance = data.get('categories', {}).get('performance', {})
            grouped_audits = performance.get('groupedAuditRefs', {})
            
            # Diagnostics
            for diagnostic in grouped_audits.get('diagnostics', []):
                score = diagnostic.get('score', 1)
                if score < 1:
                    issues.append(self._create_issue_from_audit(diagnostic, 'diagnostic'))

            # Opportunities
            for opportunity in grouped_audits.get('opportunities', []):
                score = opportunity.get('score', 1)
                if score < 1:
                    issues.append(self._create_issue_from_audit(opportunity, 'opportunity'))
        
        except Exception as e:
            print(f"Error extracting from grouped audits: {str(e)}")
        
        # Extract from poor metrics
        issues.extend(self._extract_poor_metrics(data))
        
        return issues
    
    def _create_issue_from_audit(self, audit: Dict, category: str) -> LighthouseIssue:
        """Create LighthouseIssue from audit data"""
        score = audit.get('score', 0)
        return LighthouseIssue(
            id=audit.get('id', 'unknown'),
            title=audit.get('title', 'Unknown Issue'),
            description=audit.get('description', ''),
            score=score,
            impact=audit.get('displayValue', ''),
            category=category,
            severity=self._calculate_severity(score),
            details=audit.get('details', {}),
            potential_savings=audit.get('metricSavings', {})
        )
    
    def _extract_poor_metrics(self, data: Dict) -> List[LighthouseIssue]:
        """Extract issues from metrics with poor performance"""
        issues = []
        metrics = data.get('Metrics', {})
        
        metric_thresholds = {
            'Largest Contentful Paint': {'threshold': 2.5, 'unit': 's', 'good_score': 75},
            'First Contentful Paint': {'threshold': 1.8, 'unit': 's', 'good_score': 75},
            'Total Blocking Time': {'threshold': 200, 'unit': 'ms', 'good_score': 90},
            'Speed Index': {'threshold': 3.4, 'unit': 's', 'good_score': 75}
        }
        
        for metric_name, config in metric_thresholds.items():
            metric_data = metrics.get(metric_name, {})
            if not metric_data:
                continue
                
            score = metric_data.get('score')
            value_str = metric_data.get('value', '0')
            
            if score == "N/A" or (isinstance(score, (int, float)) and score >= config['good_score']):
                continue
            
            numeric_value = self._extract_numeric_value(value_str, config['unit'])
            
            if numeric_value > config['threshold'] or (isinstance(score, (int, float)) and score < config['good_score']):
                issues.append(LighthouseIssue(
                    id=f"{metric_name.lower().replace(' ', '-')}-issue",
                    title=f"Poor {metric_name} Performance",
                    description=f"{metric_name} is {numeric_value:.1f}{config['unit']}, exceeding recommended {config['threshold']}{config['unit']}",
                    score=score/100 if isinstance(score, (int, float)) else 0,
                    impact=f"{numeric_value:.1f}{config['unit']}",
                    category='core-web-vital',
                    severity=self._calculate_severity_from_metric(numeric_value, config['threshold']),
                    details={'metric_value': numeric_value, 'threshold': config['threshold']}
                ))
        
        return issues
    
    def _extract_numeric_value(self, value_str: str, unit: str) -> float:
        """Extract numeric value from metric strings"""
        try:
            if not value_str or value_str in ('N/A', 'NA', None):
                return 0.0
            cleaned = re.sub(r'[^\d.]', '', str(value_str))
            value = float(cleaned) if cleaned else 0.0
            
            # Convert ms to s if needed
            if unit == 's' and 'ms' in str(value_str).lower():
                value = value / 1000
                
            return value
        except:
            return 0.0
    
    def _calculate_severity(self, score: float) -> str:
        """Calculate severity based on score"""
        if score <= 0.25:
            return 'critical'
        elif score <= 0.5:
            return 'high'
        elif score <= 0.75:
            return 'medium'
        else:
            return 'low'
    
    def _calculate_severity_from_metric(self, value: float, threshold: float) -> str:
        """Calculate severity based on how much value exceeds threshold"""
        ratio = value / threshold
        if ratio >= 3:
            return 'critical'
        elif ratio >= 2:
            return 'high'
        elif ratio >= 1.5:
            return 'medium'
        else:
            return 'low'
    
    def _create_issues_summary(self, issues: List[LighthouseIssue]) -> Dict:
        """Create summary of issues"""
        summary = {
            'total_issues': len(issues),
            'by_severity': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0},
            'by_category': {},
            'core_web_vitals_issues': 0
        }
        
        for issue in issues:
            summary['by_severity'][issue.severity] += 1
            summary['by_category'][issue.category] = summary['by_category'].get(issue.category, 0) + 1
            
            if issue.category == 'core-web-vital':
                summary['core_web_vitals_issues'] += 1
        
        return summary
    
    def _analyze_issues_with_ai(self, issues: List[LighthouseIssue], domain: str, device_type: str, performance_score: float) -> Dict:
        """Analyze issues using AI"""
        try:
            # Prepare issues for AI analysis
            issues_data = []
            for issue in issues:
                issues_data.append({
                    'id': issue.id,
                    'title': issue.title,
                    'description': issue.description,
                    'score': issue.score,
                    'impact': issue.impact,
                    'category': issue.category,
                    'severity': issue.severity
                })
            
            prompt = self._build_analysis_prompt(domain, device_type, performance_score, issues_data)
            
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=4000
                )
            )
            
            if response and response.text:
                return self._parse_ai_response(response.text)
            else:
                return self._create_fallback_analysis(issues)
                
        except Exception as e:
            return {"error": f"AI analysis failed: {str(e)}", "fallback": self._create_fallback_analysis(issues)}
    
    def _build_analysis_prompt(self, domain: str, device_type: str, performance_score: float, issues_data: List[Dict]) -> str:
        """Build prompt for AI analysis"""
        issues_text = ""
        for i, issue in enumerate(issues_data, 1):
            issues_text += f"""
Issue #{i}: {issue['title']}
- Category: {issue['category']}
- Severity: {issue['severity']}
- Score: {issue['score']:.2f}/1.0
- Impact: {issue['impact']}
- Description: {issue['description']}
"""
        
        return f"""
Analyze these Lighthouse performance issues for {domain} ({device_type} device, current score: {performance_score}/100).

ISSUES FOUND:
{issues_text}

Provide analysis in JSON format:
{{
    "priority_fixes": [
        {{
            "issue_title": "title",
            "priority_rank": 1,
            "what_is_wrong": "clear explanation",
            "how_to_fix": {{
                "steps": ["specific step 1", "specific step 2"],
                "technical_details": "implementation details"
            }},
            "expected_improvement": "performance score points gained",
            "difficulty": "easy/medium/hard",
            "time_estimate": "time to implement"
        }}
    ],
    "quick_wins": ["immediate fixes that are easy to implement"],
    "biggest_impact": ["fixes that will improve performance score the most"],
    "overall_strategy": "recommended approach to tackle these issues"
}}

Focus on actionable, specific recommendations prioritized by impact and ease of implementation.
"""
    
    def _parse_ai_response(self, response_text: str) -> Dict:
        """Parse AI response"""
        try:
            cleaned = response_text.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:-3].strip()
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:-3].strip()
            
            return json.loads(cleaned)
        except:
            return {"error": "Failed to parse AI response", "raw_response": response_text[:500]}
    
    def _create_fallback_analysis(self, issues: List[LighthouseIssue]) -> Dict:
        """Create basic analysis when AI fails"""
        prioritized = sorted(issues, key=lambda x: (
            {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}[x.severity],
            x.score
        ))
        
        return {
            "priority_fixes": [
                {
                    "issue_title": issue.title,
                    "priority_rank": i + 1,
                    "severity": issue.severity,
                    "score": issue.score,
                    "basic_recommendation": issue.description
                }
                for i, issue in enumerate(prioritized[:5])
            ],
            "note": "Basic analysis - AI processing failed"
        }

# API
app = Flask(__name__)
CORS(app)

@app.route('/analyze-issues', methods=['POST'])
def analyze_issues():
    try:
        lighthouse_data = request.json
        if not lighthouse_data:
            return jsonify({"error": "No Lighthouse data provided"}), 400
        
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            return jsonify({"error": "GEMINI_API_KEY not configured"}), 500
            
        analyzer = LighthouseIssueAnalyzer(api_key)
        results = analyzer.analyze_lighthouse_issues(lighthouse_data)
        return jsonify(results)
        
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "issue-analyzer-and-Recommender"})

def test_analyzer(input_file: str = "report.json"):
    """Test the analyzer"""
    try:
        with open(input_file, 'r') as f:
            lighthouse_data = json.load(f)
        
        analyzer = LighthouseIssueAnalyzer()
        results = analyzer.analyze_lighthouse_issues(lighthouse_data)
        
        print("="*50)
        print("LIGHTHOUSE ISSUE ANALYSIS RESULTS")
        print("="*50)
        print(json.dumps(results, indent=2))
        
        # Save results
        output_file = f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {output_file}")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'api':
        app.run(debug=True, port=5000)
    else:
        test_analyzer(sys.argv[1] if len(sys.argv) > 1 else "report.json")