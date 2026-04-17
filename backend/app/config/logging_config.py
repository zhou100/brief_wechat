import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from flask import request, current_app, g

def setup_logging(app):
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # Create custom formatter that includes request ID
    formatter = RequestFormatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(request_id)s%(message)s'
    )
    error_formatter = RequestFormatter(
        '[%(asctime)s] %(levelname)s in %(module)s [in %(pathname)s:%(lineno)d]:\n%(request_id)s%(message)s'
    )

    # Configure file handler for all logs
    all_logs_file = os.path.join(logs_dir, "app.log")
    file_handler = RotatingFileHandler(all_logs_file, maxBytes=1024 * 1024, backupCount=10)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    # Configure error-specific file handler
    error_logs_file = os.path.join(logs_dir, "error.log")
    error_file_handler = RotatingFileHandler(error_logs_file, maxBytes=1024 * 1024, backupCount=10)
    error_file_handler.setFormatter(error_formatter)
    error_file_handler.setLevel(logging.ERROR)
    app.logger.addHandler(error_file_handler)

    # Set base logging level
    app.logger.setLevel(logging.INFO)

    # Log application startup
    app.logger.info(f"Application started at {datetime.now().isoformat()}")

class RequestFormatter(logging.Formatter):
    def format(self, record):
        if hasattr(record, 'request_id'):
            record.request_id = f"[Request ID: {record.request_id}] "
        else:
            record.request_id = ""
        return super().format(record)

def log_request_info(response):
    """Log request information including status code, method, and path"""
    status_code = response[1] if isinstance(response, tuple) else response.status_code
    level = logging.WARNING if status_code >= 400 else logging.INFO
    
    message = f"Status: {status_code}, Method: {request.method}, Path: {request.path}"
    if status_code >= 400:
        error_msg = response[0].get_json().get('error', 'Unknown error') if isinstance(response, tuple) else response.get_json().get('error', 'Unknown error')
        message += f", Error: {error_msg}"
    
    record = logging.LogRecord(
        name=current_app.logger.name,
        level=level,
        pathname=__file__,
        lineno=0,
        msg=message,
        args=(),
        exc_info=None
    )
    record.request_id = getattr(request, 'request_id', 'NO_REQUEST_ID')
    current_app.logger.handle(record)
    return response

def get_request_id():
    """Generate a unique request ID"""
    return datetime.now().strftime('%Y%m%d%H%M%S-') + os.urandom(4).hex()

def log_api_call(endpoint_name, duration_ms, response):
    """Log API call details"""
    request_id = getattr(g, 'request_id', '')
    if isinstance(response, tuple):
        status_code = response[1]
        response_data = response[0].get_json() if hasattr(response[0], 'get_json') else str(response[0])
    else:
        status_code = response.status_code
        response_data = response.get_json() if hasattr(response, 'get_json') else str(response)
    
    message = (
        f"[{request_id}] {endpoint_name} completed in {duration_ms:.2f}ms "
        f"with status {status_code}"
    )
    
    level = logging.INFO if status_code < 400 else logging.ERROR
    current_app.logger.log(level, message)
    return status_code
