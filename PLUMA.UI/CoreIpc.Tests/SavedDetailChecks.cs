using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using PLUMA.UI;

internal static class SavedDetailChecks
{
    internal static void Run(Action<bool,string> check)
    {
        string task=Guid.NewGuid().ToString("D"), request=Guid.NewGuid().ToString("D");
        var selected=new CoreRequestProtocol.UndoSelection(task,1,new string('a',64),"Restore captured move file.");
        var action=new CoreRequestProtocol.SavedAction(1,0,"move_file","{}","native_api","MEDIUM","ALLOW",
            null,null,1,"Moved one owned file.",null,null,true,"file_readback","Read back.",true,false,null,null,null,null,null,null,selected);
        var detail=new CoreRequestProtocol.SavedTaskDetail(1,"task_detail",request,task,Guid.NewGuid().ToString("D"),
            null,null,null,true,0,[],[action],false,1);
        var options=new JsonSerializerOptions { PropertyNamingPolicy=JsonNamingPolicy.SnakeCaseLower };
        string wire=JsonSerializer.Serialize(detail,options);
        check(CoreRequestProtocol.SavedTaskDetail.Parse(Encoding.UTF8.GetBytes(wire)).Actions[0].Selection==selected,
            "saved detail retains exact selected task/action/material identity");
        foreach(Action<JsonObject> mutate in new Action<JsonObject>[] {
            n=>n.Remove("cleanup_complete"),n=>n["extra"]="private",n=>n["cleanup_unresolved"]=1,
            n=>n["actions"]![0]!.AsObject().Remove("verified"),n=>n["actions"]![0]!["claim_state"]="invented",
            n=>n["actions"]![0]!["undo_available"]=false,n=>n["actions"]![0]!["duration_ms"]=-1,
            n=>n["actions"]![0]!["selection"]!["target_task_id"]=Guid.NewGuid().ToString("D"),
            n=>n["next_action_id"]=0 })
        {
            var node=JsonNode.Parse(wire)!.AsObject();mutate(node);
            try { CoreRequestProtocol.SavedTaskDetail.Parse(Encoding.UTF8.GetBytes(node.ToJsonString()));throw new Exception("Invalid saved facts accepted."); }
            catch(JsonException) { check(true,"inconsistent saved detail and selection refuse before presentation"); }
        }
        using var frame=JsonDocument.Parse(new CoreRequestProtocol.UndoSubmission(request,selected).ToMessage());
        check(frame.RootElement.GetProperty("message_type").GetString()=="undo_submit" && !frame.RootElement.TryGetProperty("text",out _),
            "selected inverse uses typed IPC rather than natural language execution");
    }
}
