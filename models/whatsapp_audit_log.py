"""
Audit Log Model for WhatsApp Operations
Provides observability and monitoring of API calls and operations
"""
from odoo import models, fields, api
from datetime import datetime, timedelta
from ..constants import PROVIDERS


class WhatsAppAuditLog(models.Model):
    """Audit log for WhatsApp operations and API calls"""
    
    _name = 'whatsapp.audit.log'
    _description = 'WhatsApp Audit Log'
    _order = 'timestamp desc'
    _rec_name = 'operation'
    
    # Operation details
    operation = fields.Selection([
        # Core operations
        ('send_text_message', 'Send Text Message'),
        ('send_media_message', 'Send Media Message'),
        ('create_group', 'Create Group'),
        ('sync_contacts', 'Sync Contacts'),
        ('sync_groups', 'Sync Groups'),
        ('process_webhook', 'Process Webhook'),
        
        # Provider API calls
        ('api_health_check', 'API Health Check'),
        ('api_get_contacts', 'API Get Contacts'),
        ('api_get_groups', 'API Get Groups'),
        ('api_send_message', 'API Send Message'),
        ('api_create_group', 'API Create Group'),
        ('api_upload_media', 'API Upload Media'),
        
        # System operations
        ('provider_validation', 'Provider Validation'),
        ('webhook_validation', 'Webhook Validation'),
        ('config_update', 'Configuration Update'),
    ], string='Operation', required=True)
    
    # Provider and user context
    provider = fields.Selection(PROVIDERS, string='Provider')
    
    user_id = fields.Many2one('res.users', string='User', index=True)
    config_id = fields.Many2one('whatsapp.provider.config', string='Configuration Used')
    
    # Execution details
    timestamp = fields.Datetime('Timestamp', default=fields.Datetime.now, required=True, index=True)
    success = fields.Boolean('Success', index=True)
    response_time = fields.Float('Response Time (seconds)', digits=(8, 3))
    
    # Request/Response details
    method = fields.Char('HTTP Method')
    endpoint = fields.Char('API Endpoint')
    request_size = fields.Integer('Request Size (bytes)')
    response_size = fields.Integer('Response Size (bytes)')
    
    # Error handling
    error_message = fields.Text('Error Message')
    error_code = fields.Char('Error Code')
    retry_count = fields.Integer('Retry Count', default=0)
    
    # Related records
    message_id = fields.Char('Message ID', index=True)
    group_id = fields.Char('Group ID')
    contact_phone = fields.Char('Contact Phone')
    
    # Metadata
    request_id = fields.Char('Request ID', help='Unique identifier for request tracing')
    session_id = fields.Char('Session ID')
    ip_address = fields.Char('IP Address')
    user_agent = fields.Char('User Agent')
    
    # Performance metrics
    cpu_time = fields.Float('CPU Time (seconds)', digits=(8, 3))
    memory_usage = fields.Integer('Memory Usage (MB)')
    
    # Auto-cleanup settings
    _auto_cleanup_days = 90  # Keep logs for 90 days by default
    
    @api.model
    def log_operation(self, operation: str, provider: str = None, success: bool = True,
                     response_time: float = None, error_message: str = None,
                     message_id: str = None, **kwargs):
        """
        Convenience method to log operations
        
        Args:
            operation: Operation type
            provider: Provider name
            success: Whether operation succeeded
            response_time: Response time in seconds
            error_message: Error message if failed
            message_id: Related message ID
            **kwargs: Additional fields
        """
        try:
            log_vals = {
                'operation': operation,
                'provider': provider,
                'success': success,
                'response_time': response_time,
                'error_message': error_message,
                'message_id': message_id,
                'user_id': self.env.user.id,
                'timestamp': fields.Datetime.now(),
            }
            
            # Add any additional fields from kwargs
            for key, value in kwargs.items():
                if key in self._fields:
                    log_vals[key] = value
            
            self.sudo().create(log_vals)
            
        except Exception as e:
            # Don't let logging failures break the main operation
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"Failed to create audit log: {e}")
    
    @api.model
    def log_api_call(self, method: str, endpoint: str, provider: str,
                    success: bool, response_time: float = None,
                    error_message: str = None, **kwargs):
        """Log API call details"""
        operation = f"api_{endpoint.split('/')[-1].lower()}" if endpoint else 'api_call'
        
        self.log_operation(
            operation=operation,
            provider=provider,
            success=success,
            response_time=response_time,
            error_message=error_message,
            method=method,
            endpoint=endpoint,
            **kwargs
        )
    
    @api.model
    def get_performance_metrics(self, hours: int = 24, provider: str = None):
        """Get performance metrics for the last N hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        domain = [('timestamp', '>=', cutoff_time)]
        if provider:
            domain.append(('provider', '=', provider))
        
        logs = self.search(domain)
        
        if not logs:
            return {
                'total_operations': 0,
                'success_rate': 0,
                'avg_response_time': 0,
                'error_count': 0
            }
        
        total_operations = len(logs)
        successful_operations = len(logs.filtered('success'))
        failed_operations = total_operations - successful_operations
        
        # Calculate average response time for successful operations
        successful_logs = logs.filtered(lambda l: l.success and l.response_time)
        avg_response_time = sum(successful_logs.mapped('response_time')) / len(successful_logs) if successful_logs else 0
        
        return {
            'total_operations': total_operations,
            'successful_operations': successful_operations,
            'failed_operations': failed_operations,
            'success_rate': (successful_operations / total_operations * 100) if total_operations else 0,
            'avg_response_time': avg_response_time,
            'error_count': failed_operations,
            'errors_by_type': self._get_error_breakdown(logs.filtered(lambda l: not l.success))
        }
    
    def _get_error_breakdown(self, failed_logs):
        """Get breakdown of errors by type"""
        error_breakdown = {}
        
        for log in failed_logs:
            error_type = log.error_code or 'unknown'
            if error_type not in error_breakdown:
                error_breakdown[error_type] = 0
            error_breakdown[error_type] += 1
        
        return error_breakdown
    
    @api.model
    def cleanup_old_logs(self, days: int = None):
        """Clean up old audit logs"""
        if days is None:
            days = self._auto_cleanup_days
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        old_logs = self.search([('timestamp', '<', cutoff_date)])
        count = len(old_logs)
        
        if old_logs:
            old_logs.unlink()
        
        return {
            'deleted_count': count,
            'cutoff_date': cutoff_date
        }
    
    @api.model
    def get_provider_health_summary(self):
        """Get health summary for all providers"""
        # Get recent logs (last hour)
        recent_time = datetime.now() - timedelta(hours=1)
        
        providers = self.search([]).mapped('provider')
        provider_health = {}
        
        for provider in set(providers):
            if not provider:
                continue
                
            recent_logs = self.search([
                ('provider', '=', provider),
                ('timestamp', '>=', recent_time)
            ])
            
            if recent_logs:
                success_rate = len(recent_logs.filtered('success')) / len(recent_logs) * 100
                avg_response_time = sum(recent_logs.filtered('response_time').mapped('response_time')) / len(recent_logs.filtered('response_time')) if recent_logs.filtered('response_time') else 0
                
                if success_rate >= 95 and avg_response_time < 5:
                    health_status = 'healthy'
                elif success_rate >= 80 and avg_response_time < 10:
                    health_status = 'degraded'
                else:
                    health_status = 'unhealthy'
            else:
                health_status = 'unknown'
                success_rate = 0
                avg_response_time = 0
            
            provider_health[provider] = {
                'status': health_status,
                'success_rate': success_rate,
                'avg_response_time': avg_response_time,
                'recent_operations': len(recent_logs)
            }
        
        return provider_health
    
    @api.model
    def get_daily_stats(self, days: int = 7):
        """Get daily operation statistics"""
        stats = []
        
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).date()
            
            day_logs = self.search([
                ('timestamp', '>=', datetime.combine(date, datetime.min.time())),
                ('timestamp', '<', datetime.combine(date + timedelta(days=1), datetime.min.time()))
            ])
            
            stats.append({
                'date': date,
                'total_operations': len(day_logs),
                'successful_operations': len(day_logs.filtered('success')),
                'failed_operations': len(day_logs.filtered(lambda l: not l.success)),
                'avg_response_time': sum(day_logs.filtered('response_time').mapped('response_time')) / len(day_logs.filtered('response_time')) if day_logs.filtered('response_time') else 0
            })
        
        return stats
    
    # Cron job for automatic cleanup
    @api.model
    def _cron_cleanup_audit_logs(self):
        """Cron job to automatically clean up old audit logs"""
        result = self.cleanup_old_logs()
        
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Audit log cleanup: deleted {result['deleted_count']} logs older than {result['cutoff_date']}")
        
        return result
