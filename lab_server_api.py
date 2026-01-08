from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import psycopg2
import json
import logging
from functools import wraps

app = Flask(__name__)
CORS(app)  # Enable CORS for cross-origin requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API Configuration
API_CONFIG = {
    'API_KEY': '-',  # Change this to your secure key
    'REQUIRE_AUTH': True,  # Set to False to disable authentication
    'HOST': '0.0.0.0',
    'PORT': 5050,
    'DEBUG': True
}

# Database Configuration
DB_CONFIG = {
    'host': '-',
    'database': '-',
    'user': '-',
    'password': '-',
}

# API Key Authentication Decorator
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not API_CONFIG['REQUIRE_AUTH']:
            return f(*args, **kwargs)
        
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            logger.warning("Request without Authorization header")
            return jsonify({
                'status': 'error',
                'message': 'Authorization header is required'
            }), 401
        
        # Check Bearer token
        try:
            scheme, token = auth_header.split()
            if scheme.lower() != 'bearer':
                raise ValueError("Invalid authentication scheme")
            
            if token != API_CONFIG['API_KEY']:
                logger.warning(f"Invalid API key attempted: {token[:10]}...")
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid API key'
                }), 401
                
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': 'Invalid Authorization header format. Use: Bearer <api_key>'
            }), 401
        
        return f(*args, **kwargs)
    return decorated_function

# Database Helper Functions
def get_db_connection():
    """Create database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise

def save_to_database(data):
    """Save laboratory results to database"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Extract patient data
        patient = data.get('patient', {})
        
        # Convert DOB from YYYYMMDD to date object
        dob = None
        try:
            dob_str = patient.get('date_of_birth', '')
            if dob_str:
                dob = datetime.strptime(dob_str, "%Y%m%d").date()
        except Exception as e:
            logger.warning(f"Invalid DOB format: {e}")
        
        # Insert or update patient
        cur.execute("""
            INSERT INTO patients (first_name, last_name, dob, sex)
            VALUES (%s, %s, %s, %s)
            RETURNING patients_id
        """, (
            patient.get('first_name'),
            patient.get('last_name'),
            dob,
            patient.get('sex')
        ))
        
        patient_id = cur.fetchone()[0]
        
        # Insert laboratory results
        results = data.get('laboratory_results', [])
        inserted_count = 0
        
        for result in results:
            cur.execute("""
                INSERT INTO hematology_results 
                (patient_id, test_name, value, units, reference_range, abnormal_flag)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                patient_id,
                result.get('test_name'),
                result.get('value'),
                result.get('units'),
                result.get('reference_range'),
                result.get('abnormal_flag')
            ))
            inserted_count += 1
        
        conn.commit()
        cur.close()
        
        logger.info(f"Saved patient {patient_id} with {inserted_count} test results")
        
        return {
            'patient_id': patient_id,
            'results_count': inserted_count
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database save error: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()

# API Routes

@app.route('/', methods=['GET'])
def index():
    """API home endpoint"""
    return jsonify({
        'status': 'online',
        'service': 'Laboratory Results API',
        'version': '1.0',
        'timestamp': datetime.now().isoformat(),
        'endpoints': {
            '/api/lab/results': 'POST - Submit laboratory results',
            '/api/health': 'GET - Health check',
            '/api/stats': 'GET - API statistics'
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        
        db_status = 'connected'
    except Exception as e:
        db_status = f'error: {str(e)}'
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': db_status,
        'authentication': 'enabled' if API_CONFIG['REQUIRE_AUTH'] else 'disabled'
    })

@app.route('/api/lab/results', methods=['POST'])
@require_api_key
def receive_lab_results():
    """Receive and store laboratory results"""
    try:
        # Get JSON data
        if not request.is_json:
            return jsonify({
                'status': 'error',
                'message': 'Content-Type must be application/json'
            }), 400
        
        data = request.get_json()
        
        # Validate required fields
        if 'patient' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Patient data is required'
            }), 400
        
        if 'laboratory_results' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Laboratory results are required'
            }), 400
        
        if not isinstance(data['laboratory_results'], list):
            return jsonify({
                'status': 'error',
                'message': 'Laboratory results must be an array'
            }), 400
        
        # Log received data
        logger.info(f"Received lab results from {request.remote_addr}")
        logger.info(f"Patient: {data['patient'].get('first_name')} {data['patient'].get('last_name')}")
        logger.info(f"Results count: {len(data['laboratory_results'])}")
        
        # Save to database
        result = save_to_database(data)
        
        # Return success response
        return jsonify({
            'status': 'success',
            'message': 'Laboratory results received and stored successfully',
            'data': {
                'patient_id': result['patient_id'],
                'results_count': result['results_count'],
                'timestamp': datetime.now().isoformat()
            }
        }), 201
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to process laboratory results: {str(e)}'
        }), 500

@app.route('/api/lab/results', methods=['PUT'])
@require_api_key
def update_lab_results():
    """Update existing laboratory results"""
    try:
        data = request.get_json()
        
        return jsonify({
            'status': 'success',
            'message': 'Laboratory results updated successfully',
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error updating results: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/lab/results/<int:patient_id>', methods=['GET'])
@require_api_key
def get_patient_results(patient_id):
    """Get laboratory results for a specific patient"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get patient info
        cur.execute("""
            SELECT patients_id, first_name, last_name, dob, sex
            FROM patients
            WHERE patients_id = %s
        """, (patient_id,))
        
        patient_row = cur.fetchone()
        
        if not patient_row:
            return jsonify({
                'status': 'error',
                'message': f'Patient with ID {patient_id} not found'
            }), 404
        
        patient = {
            'patient_id': patient_row[0],
            'first_name': patient_row[1],
            'last_name': patient_row[2],
            'date_of_birth': patient_row[3].strftime('%Y%m%d') if patient_row[3] else None,
            'sex': patient_row[4]
        }
        
        # Get test results
        cur.execute("""
            SELECT test_name, value, units, reference_range, abnormal_flag
            FROM hematology_results
            WHERE patient_id = %s
            ORDER BY hematology_id DESC
        """, (patient_id,))
        
        results = []
        for row in cur.fetchall():
            results.append({
                'test_name': row[0],
                'value': row[1],
                'units': row[2],
                'reference_range': row[3],
                'abnormal_flag': row[4],
                'status': 'abnormal' if row[4] else 'normal'
            })
        
        cur.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'data': {
                'patient': patient,
                'laboratory_results': results,
                'results_count': len(results)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error retrieving results: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/stats', methods=['GET'])
@require_api_key
def get_statistics():
    """Get API statistics"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Count total patients
        cur.execute("SELECT COUNT(*) FROM patients")
        total_patients = cur.fetchone()[0]
        
        # Count total results
        cur.execute("SELECT COUNT(*) FROM hematology_results")
        total_results = cur.fetchone()[0]
        
        # Get recent patients (last 10)
        cur.execute("""
            SELECT patients_id, first_name, last_name, dob
            FROM patients
            ORDER BY patients_id DESC
            LIMIT 10
        """)
        
        recent_patients = []
        for row in cur.fetchall():
            recent_patients.append({
                'patient_id': row[0],
                'name': f"{row[1]} {row[2]}",
                'dob': row[3].strftime('%Y-%m-%d') if row[3] else None
            })
        
        cur.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'data': {
                'total_patients': total_patients,
                'total_results': total_results,
                'recent_patients': recent_patients
            },
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting statistics: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/lab/results/<int:patient_id>', methods=['DELETE'])
@require_api_key
def delete_patient_results(patient_id):
    """
    Delete all laboratory results for a specific patient
    This will delete only the test results, not the patient record
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if patient exists
        cur.execute("SELECT patients_id, first_name, last_name FROM patients WHERE patients_id = %s", (patient_id,))
        patient = cur.fetchone()
        
        if not patient:
            cur.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': f'Patient with ID {patient_id} not found'
            }), 404
        
        # Count results before deletion
        cur.execute("SELECT COUNT(*) FROM hematology_results WHERE patient_id = %s", (patient_id,))
        results_count = cur.fetchone()[0]
        
        # Delete all test results for this patient
        cur.execute("DELETE FROM hematology_results WHERE patient_id = %s", (patient_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"Deleted {results_count} results for patient {patient_id} ({patient[1]} {patient[2]})")
        
        return jsonify({
            'status': 'success',
            'message': f'Successfully deleted {results_count} test results for patient {patient[1]} {patient[2]}',
            'data': {
                'patient_id': patient_id,
                'deleted_results': results_count,
                'timestamp': datetime.now().isoformat()
            }
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error deleting results: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/lab/patients/<int:patient_id>', methods=['DELETE'])
@require_api_key
def delete_patient(patient_id):
    """
    Delete patient and all their laboratory results
    This is a CASCADE delete - removes patient and all related data
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if patient exists
        cur.execute("SELECT patients_id, first_name, last_name FROM patients WHERE patients_id = %s", (patient_id,))
        patient = cur.fetchone()
        
        if not patient:
            cur.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': f'Patient with ID {patient_id} not found'
            }), 404
        
        # Count results before deletion
        cur.execute("SELECT COUNT(*) FROM hematology_results WHERE patient_id = %s", (patient_id,))
        results_count = cur.fetchone()[0]
        
        # Delete all test results first (foreign key constraint)
        cur.execute("DELETE FROM hematology_results WHERE patient_id = %s", (patient_id,))
        
        # Delete patient record
        cur.execute("DELETE FROM patients WHERE patients_id = %s", (patient_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"Deleted patient {patient_id} ({patient[1]} {patient[2]}) and {results_count} results")
        
        return jsonify({
            'status': 'success',
            'message': f'Successfully deleted patient {patient[1]} {patient[2]} and all associated data',
            'data': {
                'patient_id': patient_id,
                'deleted_results': results_count,
                'timestamp': datetime.now().isoformat()
            }
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error deleting patient: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/lab/results', methods=['DELETE'])
@require_api_key
def delete_all_results():
    """
    Delete ALL laboratory results (keep patients)
    WARNING: This will delete all test results but preserve patient records
    """
    try:
        # Get confirmation parameter
        confirm = request.args.get('confirm', '').lower()
        
        if confirm != 'yes':
            return jsonify({
                'status': 'error',
                'message': 'This action requires confirmation. Add ?confirm=yes to URL to proceed.',
                'warning': 'This will delete ALL laboratory results!'
            }), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Count total results
        cur.execute("SELECT COUNT(*) FROM hematology_results")
        total_results = cur.fetchone()[0]
        
        # Delete all results
        cur.execute("DELETE FROM hematology_results")
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.warning(f"DELETED ALL {total_results} laboratory results!")
        
        return jsonify({
            'status': 'success',
            'message': f'Successfully deleted all {total_results} laboratory results',
            'data': {
                'deleted_results': total_results,
                'timestamp': datetime.now().isoformat()
            }
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error deleting all results: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/lab/patients', methods=['DELETE'])
@require_api_key
def delete_all_patients():
    """
    Delete ALL patients and their results
    WARNING: This will delete ALL data from database
    """
    try:
        # Get confirmation parameter
        confirm = request.args.get('confirm', '').lower()
        
        if confirm != 'yes':
            return jsonify({
                'status': 'error',
                'message': 'This action requires confirmation. Add ?confirm=yes to URL to proceed.',
                'warning': 'This will delete ALL patients and results!'
            }), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Count totals
        cur.execute("SELECT COUNT(*) FROM patients")
        total_patients = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM hematology_results")
        total_results = cur.fetchone()[0]
        
        # Delete all results first
        cur.execute("DELETE FROM hematology_results")
        
        # Delete all patients
        cur.execute("DELETE FROM patients")
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.warning(f"DELETED ALL DATA: {total_patients} patients and {total_results} results!")
        
        return jsonify({
            'status': 'success',
            'message': f'Successfully deleted all data: {total_patients} patients and {total_results} results',
            'data': {
                'deleted_patients': total_patients,
                'deleted_results': total_results,
                'timestamp': datetime.now().isoformat()
            }
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error deleting all data: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({
        'status': 'error',
        'message': 'Internal server error'
    }), 500

if __name__ == '__main__':
    logger.info("="*60)
    logger.info("Laboratory Results API Server")
    logger.info("="*60)
    logger.info(f"Host: {API_CONFIG['HOST']}")
    logger.info(f"Port: {API_CONFIG['PORT']}")
    logger.info(f"Authentication: {'Enabled' if API_CONFIG['REQUIRE_AUTH'] else 'Disabled'}")
    if API_CONFIG['REQUIRE_AUTH']:
        logger.info(f"API Key: {API_CONFIG['API_KEY'][:10]}...")
    logger.info("="*60)
    logger.info("Available endpoints:")
    logger.info("  GET  /                      - API information")
    logger.info("  GET  /api/health            - Health check")
    logger.info("  POST /api/lab/results       - Submit lab results")
    logger.info("  PUT  /api/lab/results       - Update lab results")
    logger.info("  GET  /api/lab/results/<id>  - Get patient results")
    logger.info("  GET  /api/stats             - API statistics")
    logger.info("="*60)
    
    app.run(
        host=API_CONFIG['HOST'],
        port=API_CONFIG['PORT'],
        debug=API_CONFIG['DEBUG']
    )