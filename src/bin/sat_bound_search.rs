//! Autonomous SAT optimization: accepts no reference cost or oracle schedule.
use ddd::{parser,problem::{DelayCostType,DelayMeasurementType},solvers::ddd::bound_search};
use std::{fs::{self,File},io::Write,path::PathBuf};
use structopt::StructOpt;

#[derive(StructOpt)]
struct Opt {
    #[structopt(long,parse(from_os_str))] instance:PathBuf,
    #[structopt(long)] objective:String,
    #[structopt(long,default_value="300")] timeout:f64,
    #[structopt(long,parse(from_os_str))] output:PathBuf,
}
fn main()->Result<(),Box<dyn std::error::Error>>{
    let opt=Opt::from_args();
    let objective=match opt.objective.as_str(){
        "finsteps123"=>DelayCostType::FiniteSteps123,"infsteps180"=>DelayCostType::InfiniteSteps180,
        "cont"=>DelayCostType::Continuous,_=>return Err("unsupported objective".into()),
    };
    let (named,_)=parser::read_txt_file(opt.instance.to_str().ok_or("invalid instance path")?,
        DelayMeasurementType::FinalStationArrival,false,None,|_|{});
    if let Some(parent)=opt.output.parent(){fs::create_dir_all(parent)?;}
    let mut trace=File::create(opt.output.with_extension("trace.jsonl"))?;
    let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||
        bound_search::solve(&named.problem,objective,opt.timeout,|query,lower,upper|{
            writeln!(trace,"{}",serde_json::json!({"query":query,"lb":lower,"ub":upper})).unwrap();
            trace.flush().unwrap();
        })));
    let value=match result {
        Ok(Ok(result))=>serde_json::to_value(result)?,
        Ok(Err(error))=>serde_json::json!({"schema":"sat-bound-search-v1","status":"invalid_solution",
            "error":format!("{:?}",error),"uses_optimum_oracle":false}),
        Err(payload)=>{
            let text=payload.downcast_ref::<String>().map(String::as_str)
                .or_else(||payload.downcast_ref::<&str>().copied()).unwrap_or("unrecognized panic");
            serde_json::json!({"schema":"sat-bound-search-v1","status":"panic","error":text,
                "uses_optimum_oracle":false})
        },
    };
    let mut value=value.as_object().unwrap().clone();
    value.insert("objective".into(),opt.objective.into());
    let success=matches!(value.get("status").and_then(|s|s.as_str()),Some("ok"|"timeout"));
    let temp=opt.output.with_extension("json.tmp");
    fs::write(&temp,serde_json::to_vec_pretty(&value)?)?;fs::rename(temp,&opt.output)?;
    if !success{std::process::exit(1);}
    Ok(())
}
