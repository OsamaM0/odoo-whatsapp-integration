"""
WhatsApp Integration Monitoring
Metrics collection and monitoring utilities
"""
import time
from collections import defaultdict
from typing import Dict, List
from odoo import models, api, fields
from ..constants import PROVIDERS
import logging

_logger = logging.getLogger(__name__)


class WhatsAppMetrics(models.AbstractModel):
    """Metrics collection service"""
    
    _name = 'whatsapp.metrics'
    _description = 'WhatsApp Metrics Service'
    
    @api.model
    def record_api_call(self, provider: str, operation: str, success: bool, 
                       response_time: float, error: str = None):
        """Record API call metrics"""
        try:
            # Create audit log entry
            self.env['whatsapp.audit.log'].sudo().create({
                'provider': provider,
                'operation': operation,
                'success': success,
                'response_time': response_time,
                'error_message': error,
                'timestamp': fields.Datetime.now(),
                'user_id': self.env.user.id,
            })
        except Exception as e:
            _logger.error(f"Failed to record metrics: {e}")
    
    @api.model
    def get_provider_stats(self, provider: str, days: int = 7) -> Dict:
        """Get provider performance statistics"""
        try:
            domain = [
                ('provider', '=', provider),
                ('timestamp', '>=', fields.Datetime.now() - 
                 fields.Datetime.to_datetime(f'{days} days ago'))
            ]
            
            logs = self.env['whatsapp.audit.log'].search(domain)
            
            total_calls = len(logs)
            successful_calls = len(logs.filtered('success'))
            failed_calls = total_calls - successful_calls
            
            response_times = [log.response_time for log in logs if log.response_time]
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            # Group by operation
            operations = defaultdict(lambda: {'total': 0, 'success': 0, 'failed': 0})
            for log in logs:
                op = operations[log.operation]
                op['total'] += 1
                if log.success:
                    op['success'] += 1
                else:
                    op['failed'] += 1
            
            return {
                'provider': provider,
                'days': days,
                'total_calls': total_calls,
                'successful_calls': successful_calls,
                'failed_calls': failed_calls,
                'success_rate': (successful_calls / total_calls * 100) if total_calls > 0 else 0,
                'avg_response_time': avg_response_time,
                'operations': dict(operations)
            }
        except Exception as e:
            _logger.error(f"Failed to get provider stats: {e}")
            return {}
    
    @api.model
    def get_message_stats(self, days: int = 7) -> Dict:
        """Get message sending statistics"""
        try:
            domain = [
                ('created_at', '>=', fields.Datetime.now() - 
                 fields.Datetime.to_datetime(f'{days} days ago'))
            ]
            
            messages = self.env['whatsapp.message'].search(domain)
            
            total_messages = len(messages)
            outbound_messages = len(messages.filtered('from_me'))
            inbound_messages = total_messages - outbound_messages
            
            # Group by status
            status_counts = defaultdict(int)
            for message in messages:
                status_counts[message.status] += 1
            
            # Group by provider
            provider_counts = defaultdict(int)
            for message in messages:
                provider_counts[message.provider] += 1
            
            # Group by message type
            type_counts = defaultdict(int)
            for message in messages:
                type_counts[message.message_type] += 1
            
            return {
                'days': days,
                'total_messages': total_messages,
                'outbound_messages': outbound_messages,
                'inbound_messages': inbound_messages,
                'status_distribution': dict(status_counts),
                'provider_distribution': dict(provider_counts),
                'type_distribution': dict(type_counts)
            }
        except Exception as e:
            _logger.error(f"Failed to get message stats: {e}")
            return {}
    
    @api.model
    def get_health_check(self) -> Dict:
        """Get system health status"""
        try:
            # Check recent errors
            recent_errors = self.env['whatsapp.audit.log'].search([
                ('success', '=', False),
                ('timestamp', '>=', fields.Datetime.now() - 
                 fields.Datetime.to_datetime('1 hour ago'))
            ])
            
            error_rate = len(recent_errors)
            
            # Check provider connectivity
            providers_status = {}
            for provider in [p[0] for p in PROVIDERS]:  # Extract provider keys from PROVIDERS constant
                try:
                    factory = self.env['whatsapp.provider.factory']
                    provider_instance = factory.get_default_provider()
                    if provider_instance and provider_instance.provider_name == provider:
                        health = provider_instance.health_check()
                        providers_status[provider] = health.get('healthy', False)
                    else:
                        providers_status[provider] = False
                except Exception:
                    providers_status[provider] = False
            
            # Overall health
            overall_healthy = (
                error_rate < 10 and  # Less than 10 errors in the last hour
                any(providers_status.values())  # At least one provider is healthy
            )
            
            return {
                'healthy': overall_healthy,
                'error_rate_last_hour': error_rate,
                'providers_status': providers_status,
                'timestamp': fields.Datetime.now().isoformat()
            }
        except Exception as e:
            _logger.error(f"Health check failed: {e}")
            return {
                'healthy': False,
                'error': str(e),
                'timestamp': fields.Datetime.now().isoformat()
            }
