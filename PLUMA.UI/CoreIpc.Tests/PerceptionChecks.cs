using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using PLUMA.UI;

internal static class PerceptionChecks
{
    internal static void Run(Action<bool,string> check)
    {
        string Id()=>Guid.NewGuid().ToString("D");
        var now=DateTimeOffset.UtcNow;
        var item=new CoreRequestProtocol.PerceptionObservation(Id(),Id(),1,Id(),Id(),123,456,789,"OwnedClass","sha256:"+new string('a',64),
            new(-100,20,100,120),1.25,new(0,0,200,100),now.ToString("O"),now.AddSeconds(3).ToString("O"),"UNIQUE",
            new(Id(),new(10,20,50,40),.97),true);
        var frame=new CoreRequestProtocol.PerceptionSnapshot(1,"perception_snapshot",Id(),[item]);
        string Wire()=>JsonSerializer.Serialize(frame,new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.SnakeCaseLower});
        check(CoreRequestProtocol.PerceptionSnapshot.Parse(Encoding.UTF8.GetBytes(Wire())).Observations.Single().RequiresTargetRevalidation,
            "perception metadata keeps actual bounds/confidence and requires native target revalidation; it grants no action authority");
        foreach(string fault in new[]{"foreign-field","outside","confidence","authority","ambiguous","missing","identity","duplicate-task"})
        {
            var node=JsonNode.Parse(Wire())!;var value=node["observations"]![0]!;
            switch(fault)
            {
                case "foreign-field":value["image_bytes"]="PRIVATE";break;
                case "outside":value["match"]!["bounds"]!["right"]=201;break;
                case "confidence":value["match"]!["confidence"]=1.1;break;
                case "authority":value["requires_target_revalidation"]=false;break;
                case "ambiguous":value["match_state"]="AMBIGUOUS";break;
                case "missing":value.AsObject().Remove("match");break;
                case "identity":value["observation_id"]="unknown";break;
                case "duplicate-task":node["observations"]!.AsArray().Add(value.DeepClone());break;
            }
            bool refused=false;try{CoreRequestProtocol.PerceptionSnapshot.Parse(Encoding.UTF8.GetBytes(node.ToJsonString()));}catch(JsonException){refused=true;}
            check(refused,"perception metadata rejects invalid evidence: "+fault);
        }
        using var request=JsonDocument.Parse(new CoreRequestProtocol.PerceptionRequest(Id()).ToMessage());
        check(request.RootElement.GetProperty("message_type").GetString()=="perception_query"&&request.RootElement.EnumerateObject().Count()==3,
            "perception query is read-only and carries no target or capture command");
    }
}
