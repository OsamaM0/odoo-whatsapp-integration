# Transaction Recovery Implementation Guide

## Problem Description

When PostgreSQL transactions enter an "aborted" state, all subsequent SQL commands fail with the error:
```
ERROR: current transaction is aborted, commands ignored until end of transaction block
```

This commonly occurs during:
- Long-running operations that hit timeout limits
- Constraint violations or other database errors
- Memory pressure causing connection issues
- Concurrent access conflicts

## Solution Overview

Implemented a robust transaction recovery mechanism with three layers of protection:

### 1. Transaction State Detection
```python
def _recover_transaction(self):
    """Recover from an aborted transaction state"""
    try:
        # Test if transaction is healthy
        self.env.cr.execute("SELECT 1")
        return True
    except Exception as e:
        if "current transaction is aborted" in str(e):
            # Transaction is aborted, attempt recovery
```

### 2. Automatic Rollback Recovery
```python
# Rollback the entire transaction
self.env.cr.rollback()
_logger.info("Transaction successfully rolled back")
return True
```

### 3. Cursor Replacement (Last Resort)
```python
# Create a new cursor from the database
new_cr = self.env.registry.cursor()
# Replace the cursor in environment
self.env = self.env(cr=new_cr)
# Close the old cursor
old_cr.close()
```

## Implementation Details

### Safe Execution Wrapper
All database operations now use `_safe_execute()` which:
1. Checks transaction health before execution
2. Attempts recovery if transaction is aborted
3. Retries operations up to 3 times with exponential backoff
4. Logs detailed error information for debugging

### Enhanced Progress Updates
```python
def _update_progress(self, step, total_steps, operation):
    def _do_update():
        self.write({
            'progress': progress,
            'current_operation': operation,
        })
        self._safe_commit()
        return True
    
    self._safe_execute(_do_update)
```

### Group Member Sync Recovery
- Each group processed independently with transaction recovery
- Batch operations wrapped in safe execution
- Individual fallback for failed batch operations
- Automatic commit after each successful group

## Key Benefits

1. **Resilience**: Automatic recovery from transaction failures
2. **Continuation**: Failed operations don't stop the entire sync process
3. **Data Integrity**: Safe commits ensure consistent state
4. **Debugging**: Enhanced logging for troubleshooting

## Error Handling Patterns

### Before (Vulnerable to Transaction Abort)
```python
try:
    with self.env.cr.savepoint():
        # Database operations
        self.env['model'].create(values)
        self.env.cr.commit()
except Exception as e:
    # If transaction is aborted, this write will also fail
    self.write({'error': str(e)})
```

### After (Transaction Recovery)
```python
def _safe_operation():
    # Database operations
    self.env['model'].create(values)
    self._safe_commit()
    return True

try:
    self._safe_execute(_safe_operation)
except Exception as e:
    # This write uses safe execution too
    self._update_progress(100, 100, f'Error: {e}')
```

## Performance Impact

- **Minimal Overhead**: Recovery only triggered when needed
- **Early Detection**: Quick transaction health checks
- **Efficient Retry**: Exponential backoff prevents resource waste
- **Batch Processing**: Maintains bulk operation benefits

## Configuration Options

### Timeout Settings
- `timeout_per_group`: Maximum time per group sync (default: 30s)
- `batch_size`: Records per batch (default: 100)
- `max_memory_usage`: Memory limit before GC (default: 500MB)

### Recovery Settings
- `max_retries`: Maximum retry attempts (default: 3)
- `retry_delay`: Base delay between retries (default: 1s)

## Monitoring and Debugging

### Log Messages to Watch
```
WARNING: Transaction is aborted, attempting recovery...
INFO: Transaction successfully rolled back
INFO: Transaction recovered with new cursor
ERROR: Failed to recover transaction state
```

### Progress Tracking
- Real-time progress updates with transaction safety
- Detailed operation logging
- Error count and message tracking
- Memory usage monitoring

## Best Practices

1. **Use Safe Execution**: Wrap all database operations in `_safe_execute()`
2. **Frequent Commits**: Commit after each logical unit of work
3. **Batch Processing**: Process large datasets in smaller batches
4. **Error Isolation**: Don't let one failure stop the entire process
5. **Resource Monitoring**: Check memory usage periodically

## Troubleshooting

### Common Issues

1. **Still Getting Transaction Errors**
   - Check if all database operations use `_safe_execute()`
   - Verify timeout settings are appropriate
   - Monitor system resources (memory, CPU)

2. **Slow Performance**
   - Increase batch sizes if memory allows
   - Adjust timeout settings for complex operations
   - Enable async processing for large datasets

3. **Data Inconsistency**
   - Review commit frequency
   - Check transaction isolation levels
   - Verify error handling doesn't skip commits

### Debug Commands
```python
# Check transaction health
wizard._recover_transaction()

# Test safe execution
wizard._safe_execute(lambda: wizard.env['whatsapp.contact'].search([]))

# Monitor progress
wizard._update_progress(50, 100, 'Testing...')
```

## Future Enhancements

1. **Connection Pooling**: Implement connection pool for better resource management
2. **Async Processing**: Full asynchronous operation support
3. **Circuit Breaker**: Prevent cascading failures
4. **Metrics Collection**: Detailed performance and error metrics
5. **Auto-tuning**: Dynamic batch size and timeout adjustment

## Testing

### Unit Tests
- Test transaction recovery under various failure conditions
- Verify safe execution retry logic
- Validate progress update reliability

### Integration Tests
- Test with large datasets (1000+ groups)
- Simulate timeout conditions
- Test concurrent access scenarios

### Performance Tests
- Measure recovery overhead
- Compare with/without transaction safety
- Memory usage under stress conditions
