## Scaling Policies

### Invocations-ScalingPolicy (scaling when at least one instance is running)
- Currently the SageMaker endpoint uses TargetTrackingScaling. We aim to maintain a Queue size of 10 (default) per instance.
- ScaleInCooldown: after removing an instance, it waits 60 (default) seconds before it can remove another instance 
- ScaleOutCooldown: after adding an instance, it waits 30 (default) seconds before it can add another instance.

### HasBacklogWithoutCapacity-ScalingPolicy (scaling back)
- If the endpoint has scaled down to zero instances, a per instance backlog cannot be calculated, so target tracking is unable to scale up from zero at all
- The HasBacklogWithoutCapacity-ScalingPolicy fixes this by adding a instance when there is one request waiting
- How is scaling down here:
    - EvaluationPeriod(=1) and DatapointsToAlarm(=1): EvaluationPeriod looks at the last N data points and if M of them breach the threshold, the instance is scaled up. In our case, we set both to 1, since if a request is waiting in the queue we want to serve it as quickly as possible. 

### Target tracking vs step scaling 

- Target tracking scaling: You pick a metric and a target value, and SageMaker automatically adds or removes instances to keep that metric near the target.

- Step scaling: You define your own CloudWatch alarms and a set of rules that say exactly how much capacity to add or remove depending on how far the metric has crossed the alarm threshold.