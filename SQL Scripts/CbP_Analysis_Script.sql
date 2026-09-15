use das
set nocount on
go
select GetDate() as 'Start Time'
print 'First GetNextCertificateBatchToValidate'

exec GetNextCertificateBatchToValidate;
-- -------------------------------
-- Action Items
-- -------------------------------
-- Action Item 1:
-- Owner:
-- Action: 

-- -----------------------------------------------------
-- CONTENTS
-- -----------------------------------------------------
-- GENERAL - ValidateSchema - if anything in schema was changed between last succesfull upgrade
-- GENERAL - Previous server upgrade history if any
-- GENERAL - Sync Percent
-- GENERAL - Average File ops and events per agent

-- -----------------------------------------------------
-- Activity Stream 1 - FILE OPERATIONS (add/edit/copy/delete)
-- -----------------------------------------------------
-- FILE OPS - What the hosts are generating (top 10 chattiest agents)
-- FILE OPS - How the server is handling what the hosts are generating
-- FILE OPS - What types of operations 
-- FILE OPS - To answer 'what type of files were generated (for extensions)'
-- FILE OPS - These are the processes that are generating all the files
-- FILE OPS - Which hosts have large queues
-- FILE OPS - Are the hosts with large queues, moving?

-- -----------------------------------------------------
-- Activity Stream 2 - Events 
-- -----------------------------------------------------
-- EVENTS - No. of Daily Events (for last 3 weeks)
-- EVENTS - File rules data breakdown
-- EVENTS - HOST_AGENT_RESTART
-- EVENTS - Events (timeout with the )
-- EVENTS -  Events: more specific break downs
-- EVENTS - Breakdown of times to receive events
-- EVENTS - Number of resyncs in last two weeks

-- -----------------------------------------------------
-- Activity Stream 3 - Scheduled Tasks
-- -----------------------------------------------------
-- SCHEDULED TASK - Scheduled Tasks Breakdown
-- SCHEDULED TASK - Determine if daily pruning process is still runing-- SCHEDULED TASK - BacklogTransactionThreshold (default value should be 10000)
-- SCHEDULED TASK - Backup History

-- -----------------------------------------------------
-- -----------------------------------------------------
-- SQL SERVER - What SQL statements are currently running V2
-- SQL SERVER - TOP 10: Tables by [SIZE]
-- SQL SERVER - TOP 20: Expensive Queries
-- SQL SERVER - TOP 20: Get Waiting Queries
-- SQL SERVER - Data Files
-- SQL SERVER - Version
-- SQL SERVER - Memory
-- -----------------------------------------------------

-- KNOWN - COMPUTER SECURITY ALERT - Alert event data breakdown
-- KNOWN - (Internal) Alert event data breakdown
-- KNOWN - If there are lots of TD events
-- KNOWN - Cert error loop
-- KNOWN - Update 7.0.1 to allow disable of Computer Security Alerts
-- KNOWN - Duplicate Deleted File Instances
-- KNOWN - Ineffective rules
-- KNOWN - Upgrade status/errors

-- FAQ - Manually Delete Cache (for pre 7.2.0)
-- FAQ - Update AB Exclusions (and antibody groups or process)
-- FAQ - Force an agent re-sync
-- ----------------------------------------------------

-- -----------------------------------------------------
-- GENERAL - Bit9Version and Sync Percent (enabled vs. disabled)
-- -----------------------------------------------------
	
	-- -----------------------------------------------------
	-- GOAL: ensure all versions are consistent (schema vs. binaries)
	-- -----------------------------------------------------


	SELECT name,value,date_modified, last_modified_by FROM shepherd_configs (NOLOCK) WHERE name in( 'ParityCenterSIDHash','ActivationKey');
	

	

	print '******* General - Confirm VERSION is correct (for server, db schema, and console) *******'
	select * from shepherd_configs (nolock) where name in ('DBSchemaVersion', 'ParityServerVersion') ;
	
	print '******* General - Confirm database schema is valid *******'
	EXEC dbo.ValidateSchema	

	print '******* General - Show previous upgrades *******'
	select top 10 * from server_upgrade_history (nolock) order by date_created desc

	-- -----------------------------------------------------
	-- GOAL: 
	--			Check the overall sync percent (for all non-deleted hosts, grouped by overall and just those in a non-disabled policy) for ones that have checked in in the last 3 days)
	-- NOTE: 
	--			hosts in disabled policies will still register a queue, but not send them.
	-- EXPECTED RANGE: 
	-- 			98% or greater.
	-- WATCHOUT: 
	--			If the sync percent is lower than 98% and the [AB_BackLog_M] below is close to zero, then the hosts are not sending their queue, this could be because:
	--			 1. you might have large number of hosts that are disconnected (is it the weekend?) 
	--			 2. you might have some network connection issues 
	-- 			 3. there is a cache consistency issue and they are either not sending or repeadetly sending the same queue items.
	-- If this is the case then look at the hosts with large queues below.
	-- -----------------------------------------------------
	print '******* General - Overall Agent Sync Percentage (for all hosts vs. only non-disabled hosts) *******'
	select 'overall (all non deleted)' 'Type', CAST(100-AVG(100.0*s.ab_queue_size/(1+s.ab_cache_size))+0.5 AS INTEGER) 'Agent Sync Percent'
		  from host_state (nolock) s
		  join hostmain (nolock) m on s.host_id = m.host_id
		  where 
		       m.deleted = 0
		       and s.last_poll_date > DATEADD(day, -3, getdate())
	union
	select 'non-disabled (defcon <> 80)' 'Type', CAST(100-AVG(100.0*s.ab_queue_size/(1+s.ab_cache_size))+0.5 AS INTEGER) 'Agent Sync Percent'
		  from host_state (nolock) s
		  join hostmain (nolock) m on s.host_id = m.host_id
		  where 
		       m.deleted = 0
		       and s.defcon_id <> 80	-- excluding those hosts that reside in a policy in disabled state
		       and s.last_poll_date > DATEADD(day, -3, getdate()); -- Including this will grab those that have been connected recently (within last 3 days)



-- -----------------------------------------------------
-- GENERAL - Average File ops and events per agent (enabled vs. disabled)
-- -----------------------------------------------------
	print '******* General - Average File Ops/Events (and count of hosts) *******'
	-- -----------------------------------------------------
	-- GOAL: 
	--			check the average FILE ops and EVENTS per agent
	-- EXPECTED RANGE: 
	-- 		Events: 50-150 / agent / day
	-- 		FILE OPS: 500-1500 / agent / day
	-- WATCHOUT: 
	--			if you see a larger than normal average amount of FILE OPS, then check:
	--			 1. Are these coming from a small subset of agents, or evenly distributed
	-- 			 2. Were there any software updates released that coinicide with the bump
	-- 			 3. Were new agents added/enabled/upgraded/etc.
	-- WATCHOUT: 
	--			if you see a larger than normal average amount of EVENTS, then check:
	-- 			 1. Were there any types of rule/policy changes recently.
	-- 			 2. Software updates
	-- 			 3. What type of events are being sent (see below in the events section for a breakdown by type/host/process/rule)
	-- -----------------------------------------------------
	declare @HostCountNotDeleted int;
	select @HostCountNotDeleted = count(1) from hostmain (nolock) where deleted = 0;
	
	
	declare @HostCount int, @AvgEvents int, @AvgFileOps int
	select @HostCount = COUNT(*) , --  ,
		@AvgFileOps = AVG(ab_queue_diff + Total_Ab_Operations_diff), 
		@AvgEvents = AVG(Total_Events_Diff) 
	FROM dbo.HostsPerformanceGUI (nolock)
	WHERE Last_Poll>DATEADD(DAY, -1, GETDATE());
	
	select 
		@HostCountNotDeleted as 'Total non-deleted host count',
		@HostCount as 'Count of Hosts Included',
		@AvgFileOps as 'Average No. of File Operations (FO)/host',
		@AvgEvents as 'Average No. of Events/host';
		

	-- -----------------------------------------------------
	-- GOAL: 
	--			Check the size of the QUEUED EVENTS and FILE OPS.  
	--			Total file ops and events queue, overall and excluding disabled. 
	--			These are key indicators because if they have a huge events queue then events will take longer to reach the console. 
	--			In addition, they both compete for finite resources.
	-- EXPECTED RANGE: 
	--			This one is difficult as it depends on the amount of endpoints.  
	--			In general if you have a medium to large size of installation (ie. > 5000 endpoints), the queues should be around or less than 1 million
	-- WATCHOUT: 
	--			another way to identify possible connectivity/network/agent cache issues is to look a the difference 
	-- 			 between the FILE OPS QUEUE and the Size of the TEMP AB Table. 
	-- 			 Specifically if there is a large QUEUE and a small temp ab table; the same things we would want look at as described above in teh SYNC percent are relevant here.
	-- NOTE:
	--			Also, if you see a large difference between the AB TEMP table and the FILE OPS queue (in particular a large file ops queue and a small ab temp table), this can indicate other issues, such as:
	--				Cache issues on agents
	--				Communication issues between agent and server (or parity server and sql server)
	--				Priority issues on agents (throttling is messed up)
	-- -----------------------------------------------------
	-- current size of ab queue size
	-- current size of event queue size
	print '******* General - Queues: File Ops and Events *******'
	declare @tmpCnt int;
	select @tmpCnt = count(1) from temp_antibody_instances (nolock);
	
	select 
			sum(ab_queue_size) as 'FO Queue 1: Agent-Side backlog (overall - including disabled)',
			sum(hs.event_queue_size) as 'EVENT (Queue) backlog (overall)',
			@tmpCnt 'FO Queue 2: Server side backlog (size of Temp AB Table) (overall - including disabled)'
		from host_state hs with (nolock)
		join hostmain hm with (nolock) on hs.host_id = hm.host_id
		where hs.last_poll_date>dateadd(day, -1, getdate()) 
			and hm.deleted = 0;

	declare @AbQueueSize int, @EventQueueSize int, @TempABSize int;
	select 
			@AbQueueSize  = sum(ab_queue_size),
			@EventQueueSize = sum(hs.event_queue_size),
			@TempABSize = @tmpCnt 
		from host_state hs with (nolock)
		join hostmain hm with (nolock) on hs.host_id = hm.host_id
		where hs.last_poll_date>dateadd(day, -1, getdate()) 
			and hs.defcon_id  <> 80
			and hm.deleted = 0;

	select 
		@AbQueueSize as 'FO Queue 1: Agent-Side backlog (excluding disabled)', 
		@EventQueueSize as 'EVENT (Queue) backlog (excluding disabled)',
		@TempABSize 'FO Queue 2: Server side backlog (size of Temp AB Table)';
		
	
	declare @CountOfEventsInLast_3Days int;
	declare @CountOfABInLast_3Days int;
	declare @CountOf1005InLast_3Days int;
	declare @CountOfABInstancesLast_3Days int;

	select @CountOfABInstancesLast_3Days = count(1) 
		from antibody_instances a with (nolock)		where a.date_created > dateadd(day, -3, getdate());


		-- Top 20 paths where NEW files are created
	print 'Top 20 paths where NEW files are created in last 3 days'
	select @CountOf1005InLast_3Days = count(*)  from events (nolock) where 	date_created> dateadd(day, -3, getdate()) and subtype = 1005;
	select @CountOfEventsInLast_3Days = count(1) from events(nolock) where  date_created> dateadd(day, -3, getdate()); 
	select @CountOfABInLast_3Days = count(1) from antibodies(nolock) where creation_date > dateadd(day, -3, getdate()); 
	
	
	select 
		getdate() 'now', 
		getutcdate() 'UTC now', 
		dateadd(day, -3, getdate()) as '3 Days Ago Date',
		@CountOfEventsInLast_3Days '@CountOfEventsInLast_3Days',
		@CountOfABInLast_3Days '@CountOfABInLast_3Days',
		@CountOf1005InLast_3Days '@CountOf1005InLast_3Days',
		@CountOfABInstancesLast_3Days '@CountOfABInstancesLast_3Days';

		;with cteFileOps as
		(		
			select 
				convert(date, execution_time) 'Date', 
				SUM(isnull(convert(bigint,output_size),0)) 'Files_Processed', 
				SUM(isnull(convert(bigint, duration_ms),0)) 'Time_Spent_Processing_Files_MS'
			from scheduled_task_executions (nolock) 
			where task_id in 
			(
				select task_id 
					from scheduled_tasks (nolock) 
					where task like 'ProcessFileInstances%'
			)
			and execution_time > dateadd(day, -21, getdate())
			group by  convert(date, execution_time)
			-- order by  convert(date, execution_time) desc
		), cteEvents as
		(
			select top 21 cast(date_created as date) 'receivedDate', count(distinct host_id) 'hosts', count(1) 'events'
				from events (nolock)
				group by cast(date_created as date)
				order by cast(date_created as date) desc
		), cteABs as
		(
			select convert(date, creation_date) 'Date_Created', count(1) 'countABs'
				from antibodies (nolock) 
				where creation_date > dateadd(day, -21, getdate())
				group by convert(date, creation_date)
				-- order by convert(date, creation_date) desc

		), cteABInst as
		(
			select convert(date, date_created) 'Date_Created', count(1) 'countABInst'
				from antibody_instances (nolock) 
				where date_created > dateadd(day, -21, getdate())
				group by convert(date, date_created)
		)
		, cteFRs as 
		(
			select convert(date, date_created) 'Date_Created', count(1) 'countFRs'
				from file_rules (nolock) 
				where date_created > dateadd(day, -21, getdate())
				group by convert(date, date_created)
				-- order by convert(date, creation_date) desc
		)
		, cteScheduledTask as
		(
			select CONVERT(date, execution_time) 'Date', SUM(duration_ms) 'Dureation_MS'
				from scheduled_task_executions (nolock)
				where execution_time > dateadd(day, -21, getdate())
				group by CONVERT(date, execution_time)
				--order by CONVERT(date, execution_time) desc
		)
		select 
				cteFileOps.Date 'Date', 
				convert(varchar(20), replace(CONVERT(varchar(20), CAST(cteFileOps.Files_Processed AS money), 1), '.00',''))  'FO_Processed', 
				cteABs.countABs 'ABs_Created',
				cteABInst.countABInst 'AbInst_Created',
				cteFRs.countFRs 'FRs_Created',
				convert(decimal(10,2), (convert(decimal(12,2), cteFileOps.Time_Spent_Processing_Files_MS) * (0.000000277778))) as 'FO_ProcessingTimeSpent(HR)',
				convert(int, (convert(decimal(10,2), cteFileOps.Files_Processed)/ convert(decimal(10,2), cteEvents.[hosts]))) 'FO_PerHost' ,
				convert(varchar(20), replace(CONVERT(varchar, CAST(cteEvents.[events] AS money), 1), '.00','')) 'E_Total', 
				cteEvents.[hosts] 'E_Hosts',
				convert(int, (convert(decimal(10,2), cteEvents.[events])/ convert(decimal(10,2), cteEvents.[hosts]))) 'E_PerHost' ,
				convert(decimal(10,2), (convert(decimal(12,2), cteScheduledTask.Dureation_MS) * (0.000000277778))) as 'ScheduleTasks_Total(HR)'
			from cteFileOps
			left join cteEvents on cteFileOps.Date = cteEvents.receivedDate
			left join cteScheduledTask on cteScheduledTask.Date = cteFileOps.Date
			left join cteABs on cteABs.Date_Created = cteFileOps.Date
			left join cteABInst on cteABInst.date_created = cteFileOps.Date
			left join cteFRs on cteFRs.Date_Created = cteFileOps.Date
			order by cteFileOps.Date desc


	select COUNT(1) 'count of [antibodies_lookup]' from dbo.antibodies_lookup(nolock);

-- -----------------------------------------------------
-- FILE OPS - How the server is handling what the hosts are generating
-- -----------------------------------------------------
	print '******* File Ops - How the server is handling what the hosts are generating *******'
	-- -----------------------------------------------------
	-- GOAL: 
	--			Check that files are being processed.
	-- NOTE: 
	--			Files are precessed by the REPORTER, using a scheduled task.  This query below shows the time/rows processed by date.  
	-- WATCHOUT: 
	--			make sure the times are recent; if you see they are not being processed, check that the reporter is on
	-- -----------------------------------------------------
	select top 30 scheduled_task_execution_id, task_id, execution_time, input_size 'Host Count', output_size 'FO Count', duration_ms 'Duration_MS' 
			from scheduled_task_executions (nolock) 
			where task_id in 
					(
						select task_id 
							from scheduled_tasks (nolock) 
							where task LIKE 'ProcessFileInstances%'
					) 
			order by execution_time desc;

	-- -----------------------------------------------------
	-- GOAL: 
	--			Show how well your system is handling what FILE OPS your agents are generating
	-- NOTE: 
	--			this provides a good look at one of the main activity streams of the server
	-- WATCHOUT: 
	-- 		1. Here you should be able to see how well your server is doing.
	-- 		2. If you see a large [AB_BackLog_M], do you know the reason?  Does it coincide with an increase in [File_Rate_M] (were there any updates release recently)
	--			Does it coincide with a shut down of the [BackLog_Rate_M]?  Was the reporter turned off? or were you running a longer than normal scheduled task
	-- 			Note: while you are doing the nightly maintenance task, you are NOT processing files.
	-- 		3. [SQL_Latency_Ms] is this in a good range?  > 1.0 ms for 2-tier and > .6 ms for single tier?
	-- 		4. Does the [AB_BackLog_M] roughly resemble the temp ab table totals (as seen above)
	--		5. Is the sync percent less than 98%, but the [AB_BackLog_M] is under a millIon?  This could imply connection issues (from agent to server or bit9 server to sql server, or CC issues)
	-- -----------------------------------------------------
	-- NOTE: 
	--			If this returns no results, make sure the Bit9 service account has these permissions:
	-- use master
	-- go
	-- grant view server state to [Test] 
	-- -----------------------------------------------------
	declare @sql1 varchar(1000);
	
	set @sql1 = '';
	set @sql1 = @sql1 + ' select top 20 '; 
	set @sql1 = @sql1 + ' File_Rate_M,'; 				-- Total file operations your agents are generating, based on the time period and projected out to the day.
	set @sql1 = @sql1 + ' Projected_File_Rate_M,'; 		-- The calculated capacity of your agents/network 
	set @sql1 = @sql1 + ' BackLog_Rate_M,'; 			-- Total files ops that have made it to the server and have been processed
	set @sql1 = @sql1 + ' Projected_BackLog_Rate_M,'; 	-- The calculated capacity of your server
	set @sql1 = @sql1 + ' AB_BackLog_M,'; 				-- What''s left over.  This is the backlog of FILE OPS that still needs to be processed.
	set @sql1 = @sql1 + ' AB_Rows_M,'; 					-- The current size of all your known FILE OPS
	IF exists (select value from shepherd_configs (nolock) where name ='DBSchemaVersion' and value like '7.2.%')
	BEGIN
		set @sql1 = @sql1 + ' SQL_Latency_Ms,'; 			-- 7.2.0 specific (comment out if pre 7.2.0): this tells you how long it takes for your Bit9 Server to communicate with the SQL SERVER
	END
	set @sql1 = @sql1 + 'date_created';
	set @sql1 = @sql1 + ' from dbo.PerformanceHistory(120)'; -- Aggregate in increments of 120 minutes.
	set @sql1 = @sql1 + ' order by Date_Created desc;'
	
	exec (@sql1);
	
	
	
	-- declare @sql1 varchar(1000);
	
	set @sql1 = '';
	set @sql1 = @sql1 + ' select top 21 '; 
	set @sql1 = @sql1 + ' File_Rate_M,'; 				-- Total file operations your agents are generating, based on the time period and projected out to the day.
	set @sql1 = @sql1 + ' Projected_File_Rate_M,'; 		-- The calculated capacity of your agents/network 
	set @sql1 = @sql1 + ' BackLog_Rate_M,'; 			-- Total files ops that have made it to the server and have been processed
	set @sql1 = @sql1 + ' Projected_BackLog_Rate_M,'; 	-- The calculated capacity of your server
	set @sql1 = @sql1 + ' AB_BackLog_M,'; 				-- What''s left over.  This is the backlog of FILE OPS that still needs to be processed.
	set @sql1 = @sql1 + ' AB_Rows_M,'; 					-- The current size of all your known FILE OPS
	IF exists (select value from shepherd_configs (nolock) where name ='DBSchemaVersion' and value like '7.2.%')
	BEGIN
		set @sql1 = @sql1 + ' SQL_Latency_Ms,'; 			-- 7.2.0 specific (comment out if pre 7.2.0): this tells you how long it takes for your Bit9 Server to communicate with the SQL SERVER
	END
	set @sql1 = @sql1 + 'date_created';
	set @sql1 = @sql1 + ' from dbo.PerformanceHistory(1440)'; -- Aggregate in increments of 120 minutes.
	set @sql1 = @sql1 + ' order by Date_Created desc;'
	
	exec (@sql1);
	
	
	declare @FileOpsBacklog int;
	select top 1 @FileOpsBacklog = AB_BackLog_M from dbo.PerformanceHistory(120) order by Date_Created desc

-- -----------------------------------------------------
-- FILE OPS - What types of operations 
-- -----------------------------------------------------
	select 
		count(1) as 'Count of File ops by TYPE (for temp ab)', 
		CASE operation_id
			WHEN 0 THEN 'Create'
			WHEN 1 THEN 'Delete'
			WHEN 2 THEN 'State Change'
			WHEN 3 THEN 'Rename'
			WHEN 4 THEN 'Rename Dir'
			WHEN 5 THEN 'Modify'
			WHEN 6 THEN 'Resynch Start'
			WHEN 7 THEN 'Resynch End'
			WHEN 8 THEN 'Bulk State Change'
			WHEN 9 THEN 'IE Create'
			WHEN 10 THEN 'IE Change'
			WHEN 11 THEN 'IEID Modify'
			WHEN 12 THEN 'Remove'
			ELSE 'Unknown'
		END AS Operation
	from temp_antibody_instances (nolock) group by operation_id order by count(1) desc

-- -----------------------------------------------------
-- FILE OPS - What the hosts are generating (top 10 chattiest agents)
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			Help identify chatty agents.  The column [total operations produced by agent since mid-night] is what you should be watching.
	-- EXPECTED RANGE: 
	--			0 - 1,000: normal to small
	--			1,000 - 5000: higher than normal; where there any recent updates? is this a developer box?  a build box?
	--			5,000+: higher than normal; 
	--			20,000+: a lot higher than normal; grab the HOST_ID and look at the type of events they are generating.
	-- -----------------------------------------------------
	print '******* File Ops - What the hosts are generating (since mid-night) *******'
	select top 10 
		host_id, 
		convert(varchar(40), host_name) 'host name', 
		(ab_queue_diff + Total_Ab_Operations_diff) as 'total operations produced by agent since mid-night',
		Total_Ab_Operations,		-- Total Antibody (AB) operations by host (includes resync and initialize)		
		total_ab_operations_diff,       -- Total AB operations by host (includes resync and initialize) since mid-night
		Total_Ab_Chg_Operations,        -- Total AB operations by host (DOES NOT includes resync and initialize)
		Total_Ab_Chg_Operations_Diff,   -- Total AB operations by host (DOES NOT includes resync and initialize) since mid-night
		Total_Events_Diff,              -- Total Events by host (includes resync and initialize) since mid-night
		ab_queue_diff,                  -- Total AB operations processed (that were in queue) by host since mid-night
		Ab_Queue_Size                   -- sum of ab_queue_size across all agent = agent backlog (with last poll date > last week)
	   from dbo.HostsPerformanceGUI (nolock)
	   order by 3 desc -- 'total operations produced by agent since mid-night'

	-- -----------------------------------------------------
	-- GOAL: 
	-- 			This breaks down the agents by buckets of sync percent.  Good to use if you are distributing new policies or agents; this can help you check when to deploy more.
	-- -----------------------------------------------------
	select
		ROUND(P.Synch_Percent/20,0)*20 as 'Sync Range',
		avg(P.Total_Ab_Operations_Diff  + P.ab_queue_diff) as 'Average total file operations produced by agents since mid-night',
		-- avg(P.Total_Ab_Chg_Operations_Diff) as 'ABDIFF',
		-- avg(P.Total_Ab_Churn) as 'ABCHURN',
		-- avg(P.Backlog_Count) as 'BACKLOG',
		Count(P.Host_ID) as '# SYSTEMS'
		from
		bit9_public.ExComputers C with(nolock) ,
		dbo.HostsPerformanceGUI P with(nolock) 
		where
		C.Computer_Id = P.host_id and
		C.Enforcement_Level not like '%disabled%' and
		P.Days_Offline < 10
		group by ROUND(P.Synch_Percent/20,0)*20
		order by ROUND(P.Synch_Percent/20,0)*20 ASC



-- -----------------------------------------------------
-- FILE OPS - Count of temp AB table
-- Are the hosts with large queues, moving? 
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			The TEMP AB table is the first place the FILE OPs land in the server, they are then processed by the reporter (in a scheduled task)
	--			Once the file operations are processed, they are removed from this table.
	-- NOTE:
	-- 			This table can be used to see how the FILE OPS queue is being handled, or to identify chatty agents.
	-- -----------------------------------------------------
	print '******* File Ops - Breakdown of the TEMP AB Table (where file operations land first, server side, before being moved to their final resting place) *******'
	select count(1) 'count of temp_antibody_instances' from dbo.temp_antibody_instances (nolock);

	select top 20 count(1) 'Count of Temp AB records', host_ID 
		from dbo.temp_antibody_instances (nolock)
	--	where host_id in ()
		GROUP BY host_id
		order by count(1) desc	;

	select count(1) 'Total Count of Temp ABs associatd to deleted or disabled hosts'
		from temp_antibody_instances (nolock) tab
		join host_state hs (nolock) on hs.host_id= tab.host_id
		join hostmain hm (nolock) on hm.host_id = tab.host_id
		where hs.defcon_id= 80 or hm.deleted = 1
		
	select count(1) as 'Count of Temp AB Instances by Operation Type',
		CASE operation_id
				WHEN 0 THEN 'Create'
				WHEN 1 THEN 'Delete'
				WHEN 2 THEN 'State Change'
				WHEN 3 THEN 'Rename'
				WHEN 4 THEN 'Rename Dir'
				WHEN 5 THEN 'Modify'
				WHEN 6 THEN 'Resynch Start'
				WHEN 7 THEN 'Resynch End'
				WHEN 8 THEN 'Bulk State Change'
				WHEN 9 THEN 'IE Create'
				WHEN 10 THEN 'IE Change'
				WHEN 11 THEN 'IEID Modify'
				WHEN 12 THEN 'Remove'
				ELSE 'Unknown'
			END AS Operation
		from dbo.temp_antibody_instances (nolock)
		group by 
			CASE operation_id
				WHEN 0 THEN 'Create'
				WHEN 1 THEN 'Delete'
				WHEN 2 THEN 'State Change'
				WHEN 3 THEN 'Rename'
				WHEN 4 THEN 'Rename Dir'
				WHEN 5 THEN 'Modify'
				WHEN 6 THEN 'Resynch Start'
				WHEN 7 THEN 'Resynch End'
				WHEN 8 THEN 'Bulk State Change'
				WHEN 9 THEN 'IE Create'
				WHEN 10 THEN 'IE Change'
				WHEN 11 THEN 'IEID Modify'
				WHEN 12 THEN 'Remove'
				ELSE 'Unknown'
			end

-- -----------------------------------------------------
-- FILE OPS - These are the processes that are generating all the files
-- 			  Are we getting lots of ms updates that should be excluded?
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			These are the processes that are generating all the files
	-- NOTE:
	-- 			Are we getting lots of ms updates that should be excluded?  This could be used to help identify things to be included in the AB exclusions, or kernal exclusions.
	-- -----------------------------------------------------
	print '******* File Ops - What processes (or parents) are generating the interesting files *******'
	select top 5 
		substring(instance_group_name,0, 40) 'Group Name', 
		COUNT(1) 'Count processes (or parents) are generating the interesting files (last 7 days)'
		from dbo.AntibodyInstancesRootsGUI (nolock)
		where first_created > DATEADD(DAY, -7, GETDATE())
		group by instance_group_name 
		order by COUNT(1) desc



	IF OBJECT_ID('tempdb..#TempEvents') IS NOT NULL DROP TABLE #TempEvents
	create table #TempEvents (id int identity(1,1), event_id bigint, event_subtype_id int, rule_id int, host_id int, antibody_id bigint, hasExecuted int, hasAb int, ReceivedTimeStamp datetime, TimeStamp datetime, path_name NVARCHAR(450) , process NVARCHAR(450));

		IF exists (select value from shepherd_configs where name ='DBSchemaVersion' and value like '7.2.%')
			begin
				insert into #TempEvents (event_id, event_subtype_id, rule_id, host_id, antibody_id, ReceivedTimeStamp, TimeStamp, path_name, process)
				select event_id, event_subtype_id, rule_id, host_id, antibody_id, ReceivedTimeStamp, TimeStamp, path_name, process_file_name
					from eventsgui(1033) e
					where e.ReceivedTimeStamp > dateadd(day, -3, getdate());

			end
		IF not exists (select value from shepherd_configs where name ='DBSchemaVersion' and value like '7.2.%')
			begin
				insert into #TempEvents (event_id, event_subtype_id, rule_id, host_id, antibody_id, ReceivedTimeStamp, TimeStamp, path_name, process)
				select event_id, event_subtype_id, rule_id, host_id, antibody_id, ReceivedTimeStamp, TimeStamp, path_name, process
					from eventsgui(1033) e
					where e.ReceivedTimeStamp > dateadd(day, -3, getdate());
			end



-- -----------------------------------------------------
-- FILE OPS - Which hosts have large queues
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			The FILE OPS QUEUE is what is used to calculate the SYNC PERCENT.  Here we are trying to identify either chatty agents, or agents that have large queues.
	---			If they have a SYNC percent that never seems to go above a certain level (and never gets into the 98%+ range, then these will be helpful)
	-- NOTE:
	-- 			Some possible reasons for a large queue
	--				1. they are recently initilized/resynced
	--				2. they are dev/build boxes that generate a lot of interesting files (on and ongoing basis)
	--				3. they have a corrupt cache
	-- -----------------------------------------------------
	print '******* File Ops - Breakdown of hosts with large QUEUES (queue size, files since midnight, and events) *******'
	-- Hosts with large queues
	select top 20 hs.ab_queue_size, hs.ab_cache_size, hs.host_id, h.hostname as 'HostName (for hosts with large queues)'
		from host_state (nolock) hs
		join hostmain (nolock) h on h.host_id = hs.host_id
		where h.deleted = 0
		-- and hs.connected = 1
		and hs.last_poll_date > dateadd(day, -3, getdate())
		and hs.ab_queue_size  > hs.ab_cache_size 
		order by hs.ab_queue_size desc;

	-- Hosts with large queues, and what they have sent since-midnight (FILE OPS)
	;with cte as
		(
			select top 20 hs.ab_queue_size, hs.ab_cache_size, hs.host_id, h.hostname
				from host_state (nolock) hs
				join hostmain (nolock) h on h.host_id = hs.host_id
				where h.deleted = 0
				-- and hs.connected = 1
				and hs.last_poll_date > dateadd(day, -3, getdate())
				and hs.ab_queue_size  > hs.ab_cache_size
				order by hs.ab_queue_size desc
		)
		select a.hostname as 'Host Name (for hosts with large queues)', a.host_id as 'Host ID', a.ab_queue_size as 'Total Queue Size', (b.ab_queue_diff + b.Total_Ab_Operations_diff) as 'Total File Ops produced by agent since mid-night (for hosts with large queues)'
			from cte a
			join dbo.HostsPerformanceGUI b with (nolock) on b.host_id = a.host_id;


	-- Hosts with large queues, and what EVENTS they are throwing
	;with cte as
		(
			select top 20 hs.ab_queue_size, hs.ab_cache_size, hs.host_id, h.hostname
				from host_state (nolock) hs
				join hostmain (nolock) h on h.host_id = hs.host_id
				where h.deleted = 0
				-- and hs.connected = 1
				and hs.last_poll_date > dateadd(day, -3, getdate())
				and hs.ab_queue_size  > hs.ab_cache_size 
				order by hs.ab_queue_size desc

		)
		select top 20 count(1) 'total events by day and [TYPE] (for hosts with large queues)', e.event_subtype_Id, s.name
			from #TempEvents e
			join cte a on a.host_id = e.host_id
			join event_subtypes (nolock) s on s.event_subtype_Id = e.event_subtype_Id
			where e.ReceivedTimeStamp > dateadd(day, -3, getdate())
				group by e.event_subtype_Id, s.name
				order by count(1) desc
			;

-- -----------------------------------------------------
-- FILE OPS - To answer 'what type of files were generated (for extensions)'
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			If you have some chatty agents, then one way to help decide if these legitimately chatty would be to identify the types of files they are generating.
	--			Are they generating a lot of java related
	-- Examples:
	-- 			.java, .jar, .class, .js => should we turn on the java updater (to exclude the chatter from java production files)
	-- -----------------------------------------------------
	print '******* FILE OPS - what type of files were generated, including a breakdown of new files *******'

	;with cte as
		(
			select b.extension
			from antibody_instances a (nolock)
			join antibodies b (nolock) on a.antibody_id = b.antibody_id
			where 
			a.date_created > dateadd(day, -3, getdate())
		)
		select top 10 count(1) 'Count', Extension
		from cte
		group by extension
		order by count(1) desc


	-- Top 20 hosts generating files for last 3 days
	print 'Top 10 hosts generating files for last 3 days'
	;with cte as 
	(
		select top 10 count(1) 'Count', a.host_id, hm.hostname 
			from antibody_instances a with (nolock)
			join hostmain hm with (nolock) on a.host_id = hm.host_id
			where 
				a.date_created > dateadd(day, -3, getdate())
			group by a.host_id, hm.hostname
			order by count(1) desc
	)
	select substring(cte.hostname,0,40) 'Top 10 hosts generating files (ab instances) for last 3 days',
		cte.host_id,
		cte.Count,
		convert(int, 100 * convert(decimal(10,2), convert(decimal(15,2), cte.Count) / convert(decimal(15,2), @CountOfABInstancesLast_3Days))) '% of @CountOfABInstancesLast_3Days'
		from cte;
		-- @CountOfABInstancesLast_3Days

	-- Top 20 hosts generating NEW files in last 3 days
	print 'Top 10 hosts generating new files for last 3 days'
	;with cte as 
	(
		select top 10  count(1) as 'Count', a.host_id, hm.hostname 
			from antibody_instances a with (nolock)
			join antibodies b with (nolock) on a.antibody_id = b.antibody_id
			join hostmain hm with (nolock) on a.host_id = hm.host_id
			where 
			b.creation_date > dateadd(day, -3, getdate())
			group by a.host_id, hm.hostname
			order by count(1) desc
	)
	select substring(cte.hostname,0,40) 'Top 10 hosts generating new files (1005) for last 3 days', 
		cte.host_id,
		cte.count,
		convert(int, 100 * convert(decimal(10,2), convert(decimal(15,2), cte.count) / convert(decimal(15,2), @CountOfABInLast_3Days))) 'Percent of @CountOfABInLast_3Days'
	 from cte;

-- -----------------------------------------------------
-- EVENTS - Overall Events Info (daily, oldest, volumn, max/min, etc.)
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			The second major activity stream has to do with EVENTS.  Events are processed by the SERVER (not the reporter).
	-- 			These scripts here show you how many events are produce per day by host.
	--			Also, they tell you the max age of the events (in the events backlog); is that very old?  Are they processing events in a timely fashion.
	-- EXPECTED RANGE: 
	--			0 - 150 (events per day per agent): normal to small
	--			150 - 300 (events per day per agent): high
	--			300+ (events per day per agent): higher than normal
	-- -----------------------------------------------------
	

	
		
	update #TempEvents 
		set #TempEvents.hasExecuted = case when isnull(ab.first_execution_date,0) = 0 then 0 else 1 end
		from #TempEvents 
		left join Antibodies ab with (nolock) on ab.antibody_id = #TempEvents.antibody_id;

	update #TempEvents 
		set #TempEvents.hasAb = case when isnull(#TempEvents.antibody_id, 0) = 0 then 0 else 1 end ;




	print '******* EVENTS - Overall Events Info (daily, oldest, volumn, max/min, etc.) *******'
	IF exists (select value from shepherd_configs with (nolock) where name ='DBSchemaVersion' and value like '7.2.%')
	BEGIN
		SELECT top 10 * FROM [dbo].[EventBacklog] ();
		IF 1 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
		BEGIN
			SELECT min(time) AS OldestEntry,
				(dbo.FastApproxRowCount('dbo.events') * 1770) / 1024 as BacklogVolume
				FROM dbo.events WITH (nolock);
		END

	END
		
	
	SELECT cast(value as bigint) 'AverageEventSize' FROM dbo.shepherd_configs WITH (nolock) WHERE name='AverageEventSize';
	SELECT task_param 'ExportGetEvents' FROM dbo.scheduled_tasks WITH (nolock) WHERE task = 'ExportGetEvents';
	select max(date_created) 'Max Event Date', MIN(date_created) 'Min Event Date' from events (nolock)
	
	/*
	print '******* EVENTS - incoming rate for last three weeks *******'
	;with cte as
	(
		select top 21 cast(receivedtimestamp as date) 'receivedDate', count(distinct host_id) 'hosts', count(1) 'events'
		from eventsgui(1033)
		group by cast(receivedtimestamp as date)
		order by cast(receivedtimestamp as date) desc
	)
	select 
		[receivedDate] as 'Received Date', 
		[hosts] 'No. Hosts', 
		replace(CONVERT(varchar, CAST([events] AS money), 1), '.00','')  'No. Events', 
		convert(decimal(10,2), (convert(decimal(10,2), [events])/ convert(decimal(10,2), [hosts]))) 'Avg Events Per Host' 
	from cte;
	*/

-- -----------------------------------------------------
-- EVENTS - Number of resyncs in last two weeks
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			To provide a ways to breakdown specific events by day.  
	-- 			This can be necessary if you need to look into system wide events that are generating an overall events rate that is higher than normal
	-- -----------------------------------------------------
	print '******* EVENTS - Number of resyncs in last two weeks (and their cause) *******'
	select top 14 CAST(timestamp as date) as date,
		COUNT(1) 'count of HOST_SYNCHRONIZATION_STARTED',
		param1 'Sync Reason'
		from eventsgui(1033) 
		where event_subtype_id = 410
		group by CAST(timestamp as date) , param1 
		order by CAST(timestamp as date) desc , param1 asc
		-- 405	HOST_AGENT_RESTART
		-- 410	HOST_SYNCHRONIZATION_STARTED
		-- 426	HOST_CACHE_CHECK_START
		-- 417	HOST_CACHE_CHECK_ERROR
		-- 432	HOST_DATABASE_ERROR
		-- enum ResyncReason                         
		-- {                           
		--        ResyncReasonUnknown = 0,                  0
		--        ResyncReasonMaxMessages,                  1      (Scenario 4)
		--        ResyncReasonPostTrickle,                  2
		--        ResyncReasonPostLevel2,                   3
		--        ResyncReasonServerRequest,                4      (Scenario 1)
		--        ResyncReasonMissingHistory,               5      (Scenario 2)
		--        ResyncReasonError,                        6
		--        ResyncReasonCLIRequest,                   7
		--        ResyncReasonServerFlush,                  8
		--        ResyncReasonLargeQueueFromCC,             9      (Scenario 4)
		--        ResyncReasonServerLast                    10
		-- };     


-- -----------------------------------------------------
-- EVENTS - Number of Agent DB Errors
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			To provide a ways to breakdown specific events by day.  
	-- 			This can be necessary if you need to look into system wide events that are generating an overall events rate that is higher than normal
	-- -----------------------------------------------------
	print '******* EVENTS - Number of Agent DB Errors (last 3 days) *******'
	select top 14 CAST(#TempEvents.ReceivedTimeStamp as date) as date,
		-- param1,
		COUNT(1) 'Count of HOST_DATABASE_ERROR'
		from #TempEvents
		where event_subtype_id = 432
		group by CAST(#TempEvents.ReceivedTimeStamp as date) --, param1 
		order by CAST(#TempEvents.ReceivedTimeStamp as date) desc --, param1 asc


-- -----------------------------------------------------
-- EVENTS - HOST_AGENT_RESTART
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			To provide a ways to breakdown specific events by day.  
	-- 			This can be necessary if you need to look into system wide events that are generating an overall events rate that is higher than normal
	-- -----------------------------------------------------
	print '******* EVENTS - HOST_AGENT_RESTART (last two weeks) *******'
	select top 10  host_id , count(1) 'Count of HOST_AGENT_RESTART'
		from #TempEvents
		where event_subtype_id = 405
		group by host_id
		order by count(1) desc


-- -----------------------------------------------------
-- EVENTS - Hosts with large EVENT QUEUES
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			Identify hosts with larege event queues.
	-- 			For those with very larege queues (> 1000 events), why are they so large?  What type of events?  From one rule?
	-- -----------------------------------------------------
	select top 10 
		hs.host_id, 
		hm.display_hostname, 
		hs.event_queue_size, 
		hs.ab_queue_size, 
		hs.ab_cache_size, 
		hs.last_poll_date, 
		hs.last_config_list_version,
		hm.host_group_id,
		defcon_id
	from host_state hs with (nolock)
	join hostmain hm with (nolock) on hs.host_id = hm.host_id
	where hm.deleted = 0 
	order by hs.event_queue_size desc
		

-- -----------------------------------------------------
-- EVENTS - Events: more specific break downs (by type, hosts, process, and rule)
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			To provide a ways to breakdown specific events by day.  
	-- 			This can be necessary if you need to look into system wide events that are generating an overall events rate that is higher than normal
	-- -----------------------------------------------------
	
	declare @CountOFTotal_TempEvents int;
	select  @CountOFTotal_TempEvents  = count(1) from #TempEvents;
	select @CountOFTotal_TempEvents 'Count of [#TempEvents], or the total events for last 3 days (from getdate())',
	@CountOf1005InLast_3Days 'Count of new files events (subtye:1005) in the last 3 days (from getdate())';

	-- Top 20 paths where NEW files are created
	print 'Top 10 process creating new files in last 3 days'
	;with cte as
	(
		select TOP 10 Path_name, count(*) 'count', sum(e.hasAb) 'sum_hasAb', sum(e.hasExecuted) 'sum_hasExecuted'
			from #TempEvents e
			where event_subtype_id=1005
			group by Path_name 
			order by count(*) desc
	)
	select 
		substring(cte.Path_name,0,100) 'Top 10 paths where NEW files (1005) are created in last 3 days', 
		cte.count 'Count',
		convert(int, 100 * convert(decimal(10,2), convert(decimal(15,2), cte.count) / convert(decimal(15,2),@CountOf1005InLast_3Days))) 'percent of @CountOf1005InLast_3Days',
		convert(int, 100 * convert(decimal(10,2), convert(decimal(15,2), cte.count) / convert(decimal(15,2),@CountOFTotal_TempEvents))) 'percent of @CountOFTotal_TempEvents',
		cte.sum_hasAb,
		cte.sum_hasExecuted
	 from cte

		
	-- Top 20 process where NEW files are created
	print 'Top 10 process creating new files in last 3 days'
	;with cte as
	(
		select TOP 10 Process, count(*) 'count', sum(e.hasAb) 'sum_hasAb', sum(e.hasExecuted) 'sum_hasExecuted'
			from #TempEvents e
			where event_subtype_id=1005 
			group by Process 
			order by count(*) desc
	)
	select 
		substring(cte.process,0,100) 'Top 10 processes creating new files (1005) in last 3 days', 
		cte.count 'Count',
		convert(int, 100 * convert(decimal(10,2), convert(decimal(15,2), cte.count) / convert(decimal(15,2),@CountOf1005InLast_3Days))) 'percent of @CountOf1005InLast_3Days',
		convert(int, 100 * convert(decimal(10,2), convert(decimal(15,2), cte.count) / convert(decimal(15,2),@CountOFTotal_TempEvents))) 'percent of @CountOFTotal_TempEvents',
		cte.sum_hasAb,
		cte.sum_hasExecuted
	 from cte
	;


	print '******* EVENTS - Events: more specific break downs (by type, hosts, process, and rule)  *******'
	-- Get total events by day and [TYPE]
	;with cte as
	(
	   select top 10 count(1) 'count', e.event_subtype_Id, s.name, sum(e.hasAb) 'sum_hasAb', sum(e.hasExecuted) 'sum_hasExecuted'
			from #TempEvents e
			join event_subtypes (nolock) s on s.event_subtype_Id = e.event_subtype_Id
			group by e.event_subtype_Id, s.name
			order by count(1) desc
	)
	select 
		cte.name 'Top 10 EVENT TYPES (for last 3 days)', 
		cte.event_subtype_id, 
		cte.count,
		convert(int, 100 * convert(decimal(10,2), convert(decimal(15,2), cte.count) / convert(decimal(15,2),@CountOFTotal_TempEvents))) 'percent of @CountOFTotal_TempEvents',
		cte.sum_hasAb,
		cte.sum_hasExecuted
		from cte;

	

	-- Get total events by day and [HOST]
	;with cte as
	(
		select top 10 count(1) 'count', e.host_id, h.hostname, sum(e.hasAb) 'sum_hasAb', sum(e.hasExecuted) 'sum_hasExecuted'
			from #TempEvents e
			left join hostmain (nolock) h on h.host_id = e.host_id
			group by e.host_id, h.hostname
			order by count(1) desc
	)
	select 
		substring(cte.hostname,0,50) 'Top 10 HOSTS generating events (for last 3 days)', 
		cte.host_id,
		cte.count,
		convert(int, 100 * convert(decimal(10,2), convert(decimal(15,2), cte.count) / convert(decimal(15,2),@CountOFTotal_TempEvents))) 'percent of @CountOFTotal_TempEvents',
		cte.sum_hasAb,
		cte.sum_hasExecuted
		from cte;

	
	
	-- Get total events by day and [PROCESS]
		;with cte as
		(
			select top 20 count(1) 'count', e.process, sum(e.hasAb) 'sum_hasAb', sum(e.hasExecuted) 'sum_hasExecuted'
				from #TempEvents e
				group by e.process
				order by count(1) desc
		)
		select 
			substring(cte.process,0,100) 'Top 10 PROCESSES generating events (for last 3 days)', 
			cte.count,
			convert(int, 100 * convert(decimal(10,2), convert(decimal(15,2), cte.count) / convert(decimal(15,2),@CountOFTotal_TempEvents))) 'percent of @CountOFTotal_TempEvents',
			cte.sum_hasAb,
			cte.sum_hasExecuted
			from cte;
			

	-- Get total events by day and [RULE]
	; with cte as
	(
		select top 20 count(1) 'count', e.rule_ID, r.name 'rule_name', sum(e.hasAb) 'sum_hasAb', sum(e.hasExecuted) 'sum_hasExecuted'
			from #TempEvents e
			left outer join rules (nolock) r on r.rule_id = e.rule_id
			group by e.rule_id, r.name
			order by count(1) desc
	)
	select 
		cte.rule_name 'Top 10 RULES generating events (for last 3 days)', 
		cte.rule_id,
		cte.count,
		convert(int, 100 * convert(decimal(10,2), convert(decimal(15,2), cte.count) / convert(decimal(15,2),@CountOFTotal_TempEvents))) 'percent of @CountOFTotal_TempEvents',
		cte.sum_hasAb,
		cte.sum_hasExecuted
		from cte;



	-- Main Publishers		
	;with cte as
	(
	   select e.event_id, e.antibody_id, e.hasAb, e.hasExecuted
			from #TempEvents e
			where e.event_subtype_id = 812
	), cte2 as
	(
		select cte.event_id, cte.antibody_id, a.publisher, cte.hasAb, cte.hasExecuted
			from cte
			join antibodies a with (nolock) on a.antibody_id = cte.antibody_id 
	),cte3 as
	(
		select 
				cte2.publisher 'Publisher_id', 
				p.name 'Name', 
				COUNT(1) 'Event_Count', 
				COUNT(distinct antibody_id)'Unique_ABIds',
				SUM(cte2.hasExecuted) 'Sum_HasExecuted'
			from cte2
			join publishers p with (Nolock) on p.publisher_id = cte2.publisher
			group by cte2.publisher, p.name
	)
	select top 10
			cte3.Publisher_id,
			cte3.Name,
			cte3.Event_Count,
			cte3.Unique_ABIds,
			cte3.Sum_HasExecuted,
			convert(int, 100 * convert(decimal(10,2), convert(decimal(15,2), cte3.Event_Count) / convert(decimal(15,2),@CountOFTotal_TempEvents))) 'percent of @CountOFTotal_TempEvents'			
		from cte3
		order by cte3.Event_Count desc
		;

-- -----------------------------------------------------
-- EVENTS - Breakdown of times to receive events
-- 			From CREATION TIME on the agent to RECEIVED TIME in the server
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			This is to help identify that events are being received in a timely fashion
	-- -----------------------------------------------------
	print '******* EVENTS - Breakdown of times to receive events *******'
	
	declare @eventSum as decimal(10,2);
	select @eventSum = count(1) from #TempEvents e 	
		
	;with cte as 
	(
	select DATEDIFF(minute, e.timestamp, e.ReceivedTimestamp) Time_diff, count(1) 'EventCount'
		from #TempEvents e
		group by DATEDIFF(minute, e.timestamp, e.ReceivedTimestamp) 
	)
	select case 
			when Time_diff < 1 then 'less than  1 min.'
			when Time_diff < 2 then 'less than  2 min.'
			when Time_diff < 5 then 'less than  5 min.'
			when Time_diff < 10 then 'less than 10 min.'
			when Time_diff < 30 then 'less than 30 min.'
			else	
				'more than 30 min.'
			end	'Description of Time Buckets'
			, sum(EventCount) 'Count of Events'		
			, CONVERT(decimal(10,2),(convert(decimal(10,2), sum(EventCount)) / @eventSum)*100.0) AS [Percent (%)]
		from cte
		group by case 
			when Time_diff < 1 then 'less than  1 min.'
			when Time_diff < 2 then 'less than  2 min.'
			when Time_diff < 5 then 'less than  5 min.'
			when Time_diff < 10 then 'less than 10 min.'
			when Time_diff < 30 then 'less than 30 min.'
			else	
				'more than 30 min.'
			end	
		order by 1 

	-- Break down of the events count [BY HOST] for those events that have taken a long time (more than 10 min.)
	--  declare @daysBackToInclude int = 2;
	declare @totalCount decimal(10,2); 

	select @totalCount = count(1) from #TempEvents e
		where DATEDIFF(minute, e.timestamp, e.ReceivedTimestamp) > 30;

	;with cte as
	(
	select count(1) 'EventCount', e.host_id, hm.display_hostname
		from #TempEvents e
		join hostmain hm with (nolock) on e.host_id = hm.host_id
		where DATEDIFF(minute, e.timestamp, e.ReceivedTimestamp) > 30
		group by e.host_id, hm.display_hostname
	)
	select top 20 EventCount 'EventCount (>30m to receive)', host_id, display_hostname, CONVERT(decimal(10,2),(convert(decimal(10,2), EventCount)/ @totalCount)*100.0) AS [Percent (%)]
		from cte 
		order by EventCount desc;

	-- Break down of the events count [BY TYPE] for those events that have taken a long time (more than 10 min.)
	;with cte as 
	(
		select e.event_id
			from #TempEvents e
			where DATEDIFF(minute, e.timestamp, e.ReceivedTimestamp) > 30
	)
	select top 20 count(1) 'total events by day and [TYPE] (>30m to receive)', e.event_subtype_Id, s.name
		from cte a
		join #TempEvents e on e.event_id = a.event_id
		join event_subtypes (nolock) s on s.event_subtype_Id = e.event_subtype_Id
		group by e.event_subtype_Id, s.name
		order by count(1) desc

-- Break down of the events count [BY HOUR OF DAY - RECEIVED TIMESTAMP] for those events that have taken a long time (more than 10 min.)
	;with cte as 
	(
	select e.event_id
		from #TempEvents e
		where DATEDIFF(minute, e.timestamp, e.ReceivedTimestamp) > 30
	)
	select top 20 count(1) 'total events by hour of the day (>30m to receive)', datepart(hour, e.receivedtimestamp) 'Hour of Day - Received Date'
		from cte a
		join #TempEvents e on e.event_id = a.event_id
		group by datepart(hour, e.receivedtimestamp)
		order by datepart(hour, e.receivedtimestamp)


-- Break down of the events count [BY HOUR OF DAY - AGENT TIMESTAMP] for those events that have taken a long time (more than 10 min.)
	;with cte as 
	(
	select e.event_id
		from #TempEvents e
		where DATEDIFF(minute, e.timestamp, e.ReceivedTimestamp) > 30
	)
	select top 20 count(1) 'total events by hour of the day (>30m to receive)', datepart(hour, e.timestamp) 'Hour of Day - AGETN TIMESTAMP'
		from cte a
		join #TempEvents e on e.event_id = a.event_id
		group by datepart(hour, e.timestamp)
		order by datepart(hour, e.timestamp)


	select  count(1) 'count of connected hosts', datediff(minute,hs.last_poll_date, getdate()) 'time since last poll'
		from host_state (nolock) hs
		join hostmain (nolock) hm on hs.host_id = hm.host_id
		where hm.deleted = 0
		and hs.defcon_id <> 80
		and hs.connected = 1
		group by datediff(minute,hs.last_poll_date, getdate());


-- -----------------------------------------------------
-- EVENTS - File rules data breakdown (Trusted Directory)
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			One reason to be receiving more than a normal amount of events is because they have defined TOO MANY RULES.
	-- 			Are they relying to heavily on trusted directories?
	-- 			Are they generating too many file specific rules?
	-- -----------------------------------------------------
	print '******* EVENTS - File rules data breakdown (Trusted Directory) *******'
	select count(1) 'file_rules count by type', 
		case 
			when source_type = 0 then 'Unknown'
			when source_type = 1 then 'Manual'
			when source_type = 2 then 'Trusted Directory'
			when source_type = 3 then 'GSR'
			when source_type = 4 then 'Imported'
			when source_type = 5 then 'API'
			when source_type = 6 then 'Event Rule'
		end
		from file_rules (nolock) 
		group by source_type
		order by count(1);

	select count(1) 'file_rules count by type (for a particular date)', 
		case 
			when source_type = 0 then 'Unknown'
			when source_type = 1 then 'Manual'
			when source_type = 2 then 'Trusted Directory'
			when source_type = 3 then 'GSR'
			when source_type = 4 then 'Imported'
			when source_type = 5 then 'API'
			when source_type = 6 then 'Event Rule'
		end
		from file_rules (nolock) 
		-- where convert(varchar, date_created, 111) = '2015-03-24'
		group by source_type
		order by count(1);


	select 'Current CL',max(version) from config_list (nolock)
	union
	select 'Rule Count', count(1) from rules (nolock) 
	union
	select 'File Rules', count(1) from file_rules(nolock)
	union
	select 'Policy Count', count(1) from HostGroupGUI (nolock)
	union
	select 'Event Rule Count',count(1)  from dbo.EventRulesGUI (nolock);


	select 
			count(1) 'Config_List Count', 
			case when host_id = 0 then 'General' else 'Host Specific' end 
		from config_list (nolock)
		group by case when host_id = 0 then 'General' else 'Host Specific' end ;

	-- --------------------------------
	-- The TD paths
	-- --------------------------------
	select 'approval_paths', host_id,* from approval_paths (nolock) -- Should give us the TD paths

	-- --------------------------------
	-- The number of file rules creatd by day
	-- --------------------------------
	select top 20 count(1) 'count of file rules created by date (from all sources)', convert(varchar, date_created, 111) 
		from file_rules (nolock)
		group by convert(varchar, date_created, 111)
		order by convert(varchar, date_created, 111) desc


	select top 20 count(1) 'count of file rules created by date (from TD)', convert(varchar, date_created, 111) 
		from file_rules (nolock)
		where source_type = 2
		group by convert(varchar, date_created, 111)
		order by convert(varchar, date_created, 111) desc

	-- Count of file rules created by TDs, and their respective host and file information
	;with cte as
	(
	select  count(1) 'count of file rules (from TD)', source_id
		from file_rules (nolock)
		where source_type = 2
		group by source_id
	)
	select top 20 a.* , h.hostname, b.pathname, b.total_files, b.crawled_files, b.description, b.deleted, b.enabled
		from cte a
		join approval_paths b (nolock) on a.source_id = b.host_id
		join hostmain h (nolock) on h.host_id = b.host_id
		order by 1 desc, 2


-- -----------------------------------------------------
-- SCHEDULED TASK - Scheduled Tasks Breakdown
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			The 3rd major activity stream is the scheduled task (controlled and run by the REPORTER)
	-- 			Are they running a lot of DRIFT reports?  Do they use them?  If not then turn them off.
	--			Do they have too many alters firing off?
	--	EXPECTED ONES:
	-- 			ProcessFileInstances1 - this is the one that handles processing files
	--			UpdateAntibodyCounts - this is expensive and run often 
	-- 			GenerateNextDriftReport - do they use DRIFT REPORTS?  If not then turn them off (they will pick up performance)
	-- 			AlertExecute - Do they have a lot of thse?  What alerts to they have turned on?  Are they using them?  If not then turn them off.
	--			ProcessEventRules - do they have a lot of rules?  Can that be tuned?
	-- -----------------------------------------------------
	print '******* SCHEDULED TASK - Scheduled Tasks Breakdown *******'
	;with cte as
	(
		select 	
				count(1) 'Count', 
				SUM(e.duration_ms) 'sum_duration_ms',
				e.task_id, 
				t.task
			from scheduled_task_executions (nolock) e
			join scheduled_tasks (nolock) t on e.task_id = t.task_id
			where execution_time > dateadd(day, -3, getdate())
			group by e.task_id, t.task
			-- order by count(1) desc
	)
	select 'Scheduled Tasks Breakdown' as 'Title',
		cte.task,
		cte.task_id,
		cte.Count,
		cte.sum_duration_ms 'Duration MS',
		convert(decimal(15,2), (convert(decimal(15,2),cte.sum_duration_ms) / (60.0 * 60.0 * 1000.0))) 'Duration HR'
		from cte order by cte.Count desc;


-- -----------------------------------------------------
-- SCHEDULED TASK - Determine if daily pruning process is still runing
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			Check to make sure the nightly daily prune process isn't still running (as while this is running they will not be processing any files)
	-- -----------------------------------------------------
	print '******* SCHEDULED TASK - Determine if daily pruning process is still runing *******'
	select value, * from shepherd_configs (nolock) where name ='DBMaintenanceInProgress' -- 1 = running, 0 = not running

-- -----------------------------------------------------
-- SCHEDULED TASK - Backup History
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			They shouldn't be running any more than 1 backup a day (full)
	--			Also, it's recommended they use SIMPLE mode for the db (instead of FULL)
	-- -----------------------------------------------------
	print '******* SCHEDULED TASK - Backup History *******'
	SELECT
			TOP 20 CONVERT(VARCHAR(10), s.backup_start_date, 111) AS Backup_Date,
			s.database_name,
			CAST(s.backup_size / 1000000 AS INT) AS "Backup_Size(MB)",
			DATEDIFF(second, s.backup_start_date, s.backup_finish_date)/3600.0  AS "Duration(Hr)",
			CASE s.[type]
				WHEN 'D' THEN 'Full'
				WHEN 'I' THEN 'Diff. database'
				WHEN 'L' THEN 'Log'
				WHEN 'F' THEN 'File/filegroup'
				WHEN 'G' THEN 'Diff. file'
				WHEN 'P' THEN 'Diff. partial'
				ELSE          'Other'
				END AS Backup_Type,
			s.server_name AS "Server_Name",
			s.recovery_model AS "Recovery_Model"
		FROM  msdb.dbo.backupset (nolock) s
		WHERE s.database_name = DB_NAME() 
		AND   s.backup_start_date > GETDATE() - 14
		ORDER BY backup_start_date DESC, backup_finish_date;

-- -----------------------------------------------------
-- KNOWN ISSUE - Duplicate Hashes
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			Identify if they have any duplicate HASHES
	-- NOTE:
	--			If they are upgrading, you should clear these out prior to the upgrade.
	-- NOTE:
	--			Getting rid of the duplicates will help with performance.
	-- -----------------------------------------------------
	print '******* KNOWN ISSUE - Duplicate Hashes *******'
	-- Duplicate Hashes
	;with cte as ( 
	SELECT a2.antibody_id as src_id, max(a1.antibody_id) as dest_id 
		FROM dbo.antibodies a1 WITH (nolock) 
		JOIN dbo.antibodies a2 WITH (nolock) ON a2.hash=a1.hash AND a2.hash_type=a1.hash_type AND a2.hash <> '' 
		GROUP BY a1.hash, a2.antibody_id, a1.hash_type HAVING COUNT(a1.hash)>1 AND max(a1.antibody_id)<>a2.antibody_id 
		) 
	select count(1) AS 'Count of DUPLICATE HASHES' FROM CTE; 
	
-- -----------------------------------------------------
-- KNOWN ISSUE - Duplicate Deleted File Instances
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			Identify if they have any duplicate deleted file ABS
	-- NOTE:
	--			If they are upgrading, you should clear these out prior to the upgrade.
	-- NOTE:
	--			Getting rid of the duplicates will help with performance.
	-- -----------------------------------------------------
	print '******* KNOWN ISSUE - Duplicate Deleted File Instances *******'
	-- SELECT top 10 host_id, pathname_id, filename_id, max(antibody_instances_deleted_id) as id 
   	-- 	FROM dbo.antibody_instances_deleted WITH(nolock) 
   	-- 	GROUP BY host_id, pathname_id, filename_id HAVING count(*)>1;

   	;with cte as
	(
	  SELECT  max(antibody_instances_deleted_id) as id 
	   		FROM dbo.antibody_instances_deleted WITH(nolock) 
	   	GROUP BY host_id, pathname_id, filename_id HAVING count(*)>1
	)
	select count(1) 'Count of duplicate deleted abs' from cte;

   	/*
	IF EXISTS (SELECT * FROM dbo.sysobjects WHERE id = OBJECT_ID(N'dbo.EliminateDuplicateDeleteFileInstances') and OBJECTPROPERTY(id, N'IsProcedure') = 1)
	       DROP PROCEDURE dbo.EliminateDuplicateDeleteFileInstances
	GO
	CREATE PROCEDURE dbo.EliminateDuplicateDeleteFileInstances(@chunkSize INTEGER=10000)
	AS
	BEGIN
	       DECLARE @cnt INTEGER, @cntTotal INTEGER
	       SET @cntTotal=0
	       EXEC dbo.DropTable '#duplicates'
	       SELECT host_id, pathname_id, filename_id, max(antibody_instances_deleted_id) as id into #duplicates 
	       FROM dbo.antibody_instances_deleted WITH(nolock) GROUP BY host_id, pathname_id, filename_id HAVING count(*)>1

	       SET ROWCOUNT @chunkSize
	       WHILE 1=1
	       BEGIN
	              DELETE FROM dbo.antibody_instances_deleted
	              WHERE antibody_instances_deleted_id in 
	              (
	                     SELECT d.antibody_instances_deleted_id 
	                     FROM #duplicates t
	                           JOIN dbo.antibody_instances_deleted d on d.host_id=t.host_id and d.pathname_id=t.pathname_id and d.filename_id=t.filename_id and d.antibody_instances_deleted_id<>t.id
	              )
	              SET @cnt=@@rowcount
	              IF @cnt=0
	                     BREAK
	              SET @cntTotal=@cntTotal+@cnt
	       END

	       PRINT 'Deleted duplicate antibody_instances_deleted: ' + CAST(@cntTotal as varchar(32))
	       SET ROWCOUNT 0

	       DROP TABLE #duplicates
	END
	GO
	*/

-- -----------------------------------------------------
-- KNOWN ISSUE - KNOWN ISSUE - Ineffective custom rules 
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			Identify if they have any ineffective custom rules
	-- NOTE:
	--			This might require custom rule remediation.
	-- -----------------------------------------------------
print '******* KNOWN ISSUE - Ineffective custom rules *******'
SELECT
    rule_id,
    name,
    hidden,
    read_only,
    master_rule_id,
    CASE WHEN ((ISNULL(exec_action_mask,0) | ISNULL(action_mask,0)) = 0)
        THEN 'Yes' ELSE 'No' END
        AS "Action Mask Problem",
    CASE WHEN (ISNULL(exec_op_type,0) | ISNULL(op_type,0) = 0)
        THEN 'Yes' ELSE 'No' END
        AS "Op Type Problem"
FROM  dbo.rules WITH (NOLOCK)
WHERE deleted = 0
AND ((ISNULL(exec_action_mask,0) | ISNULL(action_mask,0)) = 0
   OR (ISNULL(exec_op_type,0) | ISNULL(op_type,0)) = 0);


-- -----------------------------------------------------
-- KNOWN - Upgrade status/errors
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			Identify if they have any prior upgrade issues
	-- NOTE:
	--			This might require Agent upgrade remediation.
	-- -----------------------------------------------------
	print '******* KNOWN ISSUE - Upgrade status *******'
	SELECT Upgrade_State, Upgrade_Status, host_agent_version, Platform, count(*) 
	FROM dbo.HostsGUI
	GROUP BY Upgrade_State, Upgrade_Status, host_agent_version, Platform
	order by 1,2,3,4


	print '******* KNOWN ISSUE - Upgrade errors *******'
	SELECT host_id, host_name, host_agent_version, Platform, Connected, Upgrade_State, Upgrade_Status, Upgrade_Error, upgrade_error_time
	FROM dbo.HostsGUI
	WHERE upgrade_Error is NOT NULL AND upgrade_status <> 'Up to date'
	order by upgrade_error_time DESC


-- -----------------------------------------------------
-- SERVER - What SQL statements are currently running V2
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			This identifies what is running currently on the sql server; you can see if there are blocks, or queries that have been running a long time.
	-- -----------------------------------------------------
	IF 1 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		print '******* SERVER - What SQL statements are currently running V2 *******'
	  -- Do not lock anything, and do not get held up by any locks.
   SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED
    -- What SQL Statements Are Currently Running?
   SELECT DISTINCT 
		'KILL ' +LTRIM(STR(session_Id)) [KILL]
		,'DBCC INPUTBUFFER(' +LTRIM(STR(session_Id)) + ')'[Buf]
      --  ,[Spid] = session_Id
      --, ecid
      , er.Start_time
	  , GETDATE() 'Now'
      , [DATABASE] = DB_NAME(sp.dbid)
      , Hostname
      , start_time
      , [USER] = nt_username
      , [Status] = er.status
      , [Wait] = wait_type
      , [Individual Query] = SUBSTRING(qt.text, er.statement_start_offset / 2,
                                       (CASE WHEN er.statement_end_offset = -1
                                             THEN LEN(CONVERT(NVARCHAR(MAX), qt.text))
                                                  * 2
                                             ELSE er.statement_end_offset
                                        END - er.statement_start_offset) / 2)
      , [Parent Query] = qt.text
      , Program = program_name
      , nt_domain
      
    FROM
        sys.dm_exec_requests er
        INNER JOIN sys.sysprocesses sp ON er.session_id = sp.spid
        CROSS APPLY sys.dm_exec_sql_text(er.sql_handle) AS qt
    WHERE
        session_Id > 50              -- Ignore system spids.    
        AND session_Id NOT IN (@@SPID)     -- Ignore this current statement.
    ORDER BY
      er.Start_time asc,2,1
	end
	IF 0 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		print '******* NO ACCESS - SERVER - What SQL statements are currently running V2 *******'
	end
	

-- -----------------------------------------------------
-- SERVER - TOP 10: Tables by [SIZE]
-- -----------------------------------------------------
	-- -----------------------------------------------------
	-- GOAL: 
	--			Do they have very large tables?  Are they the expected ones?  Do they have event/file ops pruning setup?
	-- -----------------------------------------------------
	IF 1 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		print '******* SERVER - TOP 10: Tables by [SIZE] *******'
		SELECT TOP 20
			t.NAME AS TableName,
			s.Name AS SchemaName,
			p.rows AS RowCounts,
			SUM(a.total_pages) * 8 AS TotalSpaceKB, 
			SUM(a.used_pages) * 8 AS UsedSpaceKB, 
			(SUM(a.total_pages) - SUM(a.used_pages)) * 8 AS UnusedSpaceKB
		FROM 
			sys.tables t
		INNER JOIN      
			sys.indexes i ON t.OBJECT_ID = i.object_id
		INNER JOIN 
			sys.partitions p ON i.object_id = p.OBJECT_ID AND i.index_id = p.index_id
		INNER JOIN 
			sys.allocation_units a ON p.partition_id = a.container_id
		LEFT OUTER JOIN 
			sys.schemas s ON t.schema_id = s.schema_id
		WHERE 
			t.NAME NOT LIKE 'dt%' 
			AND t.is_ms_shipped = 0
			AND i.OBJECT_ID > 255 
		GROUP BY 
			t.Name, s.Name, p.Rows
		ORDER BY 
			3 desc -- Rows
			-- 5 desc -- Size
	end
	IF 0 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		print '******* NO ACCESS - SERVER - TOP 10: Tables by [SIZE] *******'
	end
	

-- -----------------------------------------------------
-- SERVER - TOP 20: Expensive Queries
-- -----------------------------------------------------
	print '******* Get Period Covered *******'
	SELECT DATEADD(ms,  -wait_time_ms, GETDATE()) AS "from approximately", 
		   GETDATE() AS "to", wait_time_ms/3600000 AS "total hours" 
	FROM sys.dm_os_wait_stats
	WHERE wait_type = 'SQLTRACE_INCREMENTAL_FLUSH_SLEEP';

	IF 1 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		print '******* SERVER - TOP 20: Expensive Queries *******'
			SELECT top 20
				ROW_NUMBER() OVER(ORDER BY total_logical_reads+total_logical_writes DESC) AS rn, 
				case when qp.dbid is null then null else object_name(st.objectid, qp.dbid) end as object_name,
				last_execution_time, 
				CAST(total_logical_reads/1000 AS INTEGER) as readsK, CAST(total_logical_writes/1000 AS INTEGER) as writesK, CAST(total_elapsed_time/1000000 AS INTEGER) as timeSec, CAST(execution_count AS INTEGER) as count, 
				CAST(100.0*(total_logical_reads+total_logical_writes) / (.01 + SUM(total_logical_reads+total_logical_writes) OVER ()) AS DECIMAL(10,1)) AS pct, 
				total_worker_time/1000000 as workerSec,
				SUBSTRING(SUBSTRING(st.text, (qs.statement_start_offset/2) + 1, ((CASE statement_end_offset WHEN -1 THEN DATALENGTH(st.text) ELSE qs.statement_end_offset END - qs.statement_start_offset)/2) + 1), 1, 1023) AS statement_text
			FROM sys.dm_exec_query_stats AS qs
				  CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
					CROSS APPLY (SELECT CONVERT(int, value) AS dbid FROM sys.dm_exec_plan_attributes(qs.plan_handle) WHERE attribute = N'dbid') AS qp
			where db_name(qp.dbid) = 'das'
			ORDER BY pct DESC
	end
	IF 0 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		print '******* NO ACCESS - SERVER - TOP 20: Expensive Queries *******'
	end
	
-- -----------------------------------------------------
-- SERVER - TOP 20: Get Waiting Queries
-- -----------------------------------------------------
	IF 1 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		print '******* SERVER - TOP 20: Get Waiting Queries *******'
		SELECT top 20 
			ROW_NUMBER() OVER(ORDER BY total_logical_reads+total_logical_writes DESC) AS rn, 
			case when qp.dbid is null then null else object_name(st.objectid, qp.dbid) end as object_name,
			last_execution_time, 
			CAST(total_logical_reads/1000 AS INTEGER) as readsK, CAST(total_logical_writes/1000 AS INTEGER) as writesK, CAST(total_elapsed_time/1000000 AS INTEGER) as timeSec, CAST(execution_count AS INTEGER) as count, 
			CAST(100.0*(total_logical_reads+total_logical_writes) / (.01 + SUM(total_logical_reads+total_logical_writes) OVER ()) AS DECIMAL(10,1)) AS pct, 
			total_worker_time/1000000 as workerSec,
			SUBSTRING(SUBSTRING(st.text, (qs.statement_start_offset/2) + 1, ((CASE statement_end_offset WHEN -1 THEN DATALENGTH(st.text) ELSE qs.statement_end_offset END - qs.statement_start_offset)/2) + 1), 1, 1023) AS statement_text
		FROM sys.dm_exec_query_stats AS qs
			  CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
				CROSS APPLY (SELECT CONVERT(int, value) AS dbid FROM sys.dm_exec_plan_attributes(qs.plan_handle) WHERE attribute = N'dbid') AS qp
		where db_name(qp.dbid) = 'das'
		ORDER BY timeSec DESC
	end
	IF 0 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		print '******* NO ACCESS - SERVER - TOP 20: Get Waiting Queries *******'
	end
	

-- -----------------------------------------------------
-- SERVER - Classify largest SQL waits (95 percentile) since last SQL server restart
-- -----------------------------------------------------
	IF 1 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		print '******* SERVER - Classify largest SQL waits (95 percentile) since last SQL server restart  *******'
		SELECT TOP 5 Friendly_Wait_Type, SUM(Wait_Time_S) AS Wait_Time_S, SUM(Pct) AS Pct from 
		(
		SELECT  
			ROW_NUMBER() OVER(ORDER BY wait_time_ms DESC) AS Ordinal,
			CASE WHEN Wait_Type LIKE 'PAGEIOLATCH_%' THEN 'Disk Read' WHEN Wait_Type LIKE 'SLEEP_BPOOL_FLUSH' THEN 'Disk Write' WHEN Wait_Type LIKE 'WRITELOG' THEN 'Logging' WHEN Wait_Type LIKE 'BACKUP%' THEN 'Backup' WHEN Wait_Type LIKE 'SOS_SCHEDULER_YIELD' THEN 'CPU' WHEN Wait_Type LIKE 'LCK_%' THEN 'Locking' ELSE Wait_Type END AS Friendly_Wait_Type,
			Wait_Type,  
			Wait_Time_ms,
			wait_time_ms/1000 AS Wait_Time_S, 
			CAST(100. * wait_time_ms / (0.001+(SUM(wait_time_ms) OVER())) AS DECIMAL(4,1)) AS Pct
		FROM sys.dm_os_wait_stats 
		WHERE wait_time_ms>0 AND wait_type NOT IN 
			('REQUEST_FOR_DEADLOCK_SEARCH', 'CLR_SEMAPHORE', 'LAZYWRITER_SLEEP', 'RESOURCE_QUEUE', 'CHECKPOINT_QUEUE', 'TRACEWRITE', 'SERVER_IDLE_CHECK',
			'SLEEP_TASK', 'SLEEP_SYSTEMTASK', 'WAITFOR', 'XE_DISPATCHER_WAIT', 'OLEDB', 'DIRTY_PAGE_POLL', 'ONDEMAND_TASK_QUEUE',
			'CLR_AUTO_EVENT', 'CLR_MANUAL_EVENT', 'XE_TIMER_EVENT', 'LOGMGR_QUEUE', 'FT_IFTS_SCHEDULER_IDLE_WAIT', 
			'DISPATCHER_QUEUE_SEMAPHORE', 'SP_SERVER_DIAGNOSTICS_SLEEP', 'ONDEMAND_TASK_QUEUE', 'PWAIT_ALL_COMPONENTS_INITIALIZED', 
			'TRANSACTION_MUTEX', 'XE_BUFFERMGR_FREEBUF_EVENT') 
			AND wait_type NOT LIKE 'BROKER_%' AND wait_type NOT LIKE 'HADR_%' AND wait_type NOT LIKE 'FT[_]%' AND wait_type NOT LIKE 'DBMIRROR%' AND wait_type NOT LIKE 'SQLTRACE_%'
		) x GROUP BY Friendly_Wait_Type ORDER BY Pct DESC
	end
	IF 0 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		print '******* NO ACCESS - SERVER - Classify largest SQL waits (95 percentile) since last SQL server restart  *******'
	end
	

-- -----------------------------------------------------
-- SQL SERVER - Data Files
-- -----------------------------------------------------
	SELECT
		'DB_NAME' = db.name,
		'FILE_NAME' = mf.name,
		'FILE_TYPE' = mf.type_desc,
		'FILE_PATH' = mf.physical_name
		, mf.size
		, mf.max_size
		, mf.growth
		, mf.state
	FROM
	sys.databases db
	INNER JOIN sys.master_files mf
	ON db.database_id = mf.database_id
	where db.name in ('tempdb', 'das');


-- -----------------------------------------------------
-- SQL SERVER - Version
-- -----------------------------------------------------
PRINT '******* SQL SERVER - version *******'
PRINT @@VERSION



-- -----------------------------------------------------
-- SQL SERVER - Memory
-- -----------------------------------------------------
PRINT '******* SQL SERVER - Memory  *******'
SELECT object_name, cntr_value
  FROM sys.dm_os_performance_counters
  WHERE counter_name IN ('Total Server Memory (KB)', 'Target Server Memory (KB)');

-- -----------------------------------------------------
-- KNOWN - COMPUTER SECURITY ALERT - Alert event data breakdown
-- -----------------------------------------------------
	select count(1) 'alert_event_data count by type', a.alert_id, t.name
		from dbo.alert_event_data (nolock) a
		left outer join alerts (nolock) t on a.alert_id = t.alert_id 
		group by a.alert_id, t.name

-- -----------------------------------------------------
-- KNOWN - (Internal) Alert event data breakdown
-- -----------------------------------------------------
	select count(1) 'count of internal events by subtype', i.subtype, t.name
		from internal_events (nolock) i
		join event_subtypes (nolock) t on t.event_subtype_id = i.subtype
		group by i.subtype, t.name
		order by count(1) desc

-- -----------------------------------------------------
-- KNOWN - What type of connection they have to the server
-- -----------------------------------------------------
	IF 1 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		SELECT Program_Name, max(net_transport) + ':' + CASE WHEN max(client_net_address)=max(local_net_address) THEN '<local machine>' ELSE '<remote machine>' END AS Protocol
			FROM sys.dm_exec_connections AS c
				JOIN sys.dm_exec_sessions AS s ON c.session_id = s.session_id 
			GROUP BY program_name
	end


-- -----------------------------------------------------
-- Disk: avg read/write stalls ms
-- -----------------------------------------------------
	IF 1 = (SELECT COUNT(1) FROM sys.fn_my_permissions(NULL, 'SERVER') WHERE permission_name = 'VIEW SERVER STATE')
	BEGIN
		print ' '
		print '******* Get Disk subsystem statistics *******'
		
		SELECT cast(mf.name as varchar(16)) as name, substring(mf.physical_name, 1, 10) as location, 
		      num_of_reads, 
		      num_of_bytes_read/1024/1024 as num_of_mbytes_read,
		      io_stall_read_ms/1000 as io_stall_read_s,
		      num_of_bytes_read/(1+num_of_reads)/1024 as avg_read_size_kb,
		      cast (io_stall_read_ms/(0.1+num_of_reads) as numeric(10, 1)) as avg_read_stall_ms,
		      num_of_writes, 
		      num_of_bytes_written/1024/1024 as num_of_mbytes_written,
		      io_stall_write_ms/1000 as io_stall_write_s,
		      num_of_bytes_written/(1+num_of_writes)/1024 as avg_write_size_kb,
		      cast (io_stall_write_ms/(0.1+num_of_writes) as numeric(10, 1)) as avg_write_stall_ms
		FROM sys.dm_io_virtual_file_stats(NULL,NULL) a
		      join sys.master_files as mf on mf.database_id = a.database_id and mf.file_id = a.file_id
		order by num_of_bytes_read+num_of_bytes_written desc
	end

-- -----------------------------------------------------
-- KNOWN - BacklogTransactionThreshold (make sure it's 10000 and not 500)
-- -----------------------------------------------------		
	-- ALSO CHECK: Server configuration propery 'BacklogTransactionThreshold' is set to 500, which is not default value of 10000 and could result in poor background processing as backglog grows.
	SELECT value 'BacklogTransactionThreshold' FROM dbo.shepherd_configs (nolock) WHERE name = 'BacklogTransactionThreshold'

-- -----------------------------------------------------
-- Exclusions, No Group and No Coelesc
-- -----------------------------------------------------			
	select 'no group host config prop',* from host_config_prop (nolock) where name = 'no group' -- To see what they currently have
	select 'Coalesced Install Patterns host config prop',* from host_config_prop (nolock) where name = 'Coalesced Install Patterns' -- To see what they currently have
	select 'ab exclusions', * from shepherd_configs  where name like 'abex%' -- To See what they currently have;
	select * from host_config_prop (nolock) where prop_text like 'exclude_event%';
	select * from scheduled_tasks (nolock) where task in ( 'dailyprunetask', 'performDatabaseMaintenance');

	if exists (select * from shepherd_configs (nolock) where name like 'ABExclusionRules_Microsoft')
		begin
			select 
				case 
					when substring(value,1,1) = '#' 
						then 'Currently Tracking Trusted MS Updates (CHECKED)' 
						else 'NOT Tracking Trusted Files (UNCHECKED)' 
				end  
			from shepherd_configs (nolock) 
			where name like 'ABExclusionRules_Microsoft'
		end
	else
		begin
			print 'Tracking Trusted MS Files - N/A (not a supported version)'
		end
	

	
-- -----------------------------------------------------
-- KNOWN - If there are lots of TD events
-- -----------------------------------------------------
	-- exec updateshepherdconfig 'LazyApprovalsFromTD', 'true'

	-- Something to try if there are lots of blocks
	-- exec updateshepherdconfig 'ReportABListThreads', '1'



-- -----------------------------------------------------
-- FAQ - CHECK PERMISSIONS
-- -----------------------------------------------------
-- SELECT * FROM sys.fn_my_permissions(NULL, 'SERVER') 


-- -----------------------------------------------------
-- KNOWN - Cert error loop
-- -----------------------------------------------------
	-- exec GetNextCertificateBatchToValidate;
	-- wait about 5 min.
	-- exec GetNextCertificateBatchToValidate;

	-- Validate the problem cert doesn't have parents
	-- SELECT cert_id from certificates where protoparent_id = xxx

	-- SELECT cert_id from certificates where parent_id = xxx

	-- Temporarily disable the cert:
	-- update certificates set next_validation_time = '2015-06-01' where cert_id = xxx



	-- declare @cert_id int;
	-- set @cert_id = 8

	-- select 'From Certificates Table', first_seen_host_id, publisher_id, * from certificates (nolock)  where cert_id = @cert_id

	-- select 'From Publishers Table', * from publishers (nolock) where publisher_id = 
	-- 	(select publisher_id from certificates where cert_id = @cert_id);
		
	-- select count(1) 'Cert count in AB table' from  antibodies (nolock) where	cert_id = @cert_id

	-- select count(1) 'Cert count in AB by host',host_id 
	-- 	from antibodies (nolock)
	-- 	where	cert_id = @cert_id
	-- 	group by host_id
		
	-- select f.filename, p.pathname, a.host_id
	-- 	from antibodies (nolock) a
	-- 	join filenames (nolock) f on a.filename_id = f.filename_id
	-- 	join pathnames (nolock) p on a.pathname_id = p.pathname_id
	-- 	where	cert_id = @cert_id

-- -----------------------------------------------------
-- KNOWN -  Update 7.0.1 to allow disable of Computer Security Alerts
-- -----------------------------------------------------
	-- update alerts set flags = 2 where name = 'Computer Security Alert' and flags = 3;-- -----------------------------------------------------
	-- Update 7.0.1 to allow disable of Computer Security Alerts
	-- -----------------------------------------------------
	-- update alerts set flags = 2 where name = 'Computer Security Alert' and flags = 3;

-- -----------------------------------------------------
-- FAQ - Manually Delete Cache (for pre 7.2.0)
-- -----------------------------------------------------
	-- 1. get on the endpoint(S) that need to re-init
	-- 2. disable tamper protect (either locally with dascli or from the console)
	---3. sc stop parity; fltmc unload paritydriver
	-- 4. del <c:\programdata\bit9\parity agent\cache*>
	-- 5. fltmc load paritydriver; sc start parity

-- -----------------------------------------------------
-- FAQ - Update AB Exclusions (and antibody groups or process)
-- -----------------------------------------------------
	-- Run following sql queries
	-- 1. To stop sendin new installer events for each csc compilation, run SQL:

	-- EXEC dbo.ChangeHostConfigProp 'No Group', 'no_group', 'explorer.exe,cmd.exe,winlogon.exe,rundll32.exe,spoolsv.exe,mmc.exe,ccapp.exe,inort.exe,isass.exe,regsvr32.exe,java.exe,javaw.exe,msmpeng.exe,csc.exe,mscorsvw.exe', 1, 1, 1
	-- select * from host_config_prop (nolock) where name = 'no group' -- To see what they currently have

	-- 2. To stop sendin csc generated files, run SQL:

	-- EXEC UpdateShepherdConfig 'ABExclusionRules', ';;c:\windows\microsoft.net\framework*\csc.exe,c:\windows\microsoft.net\framework*\mscorsvw.exe;'
	-- select * from shepherd_configs  where name like 'abex%' -- To See what they currently have

	-- 3. Coalesced pattern
	-- EXEC dbo.ChangeHostConfigProp 'Coalesced Install Patterns', 'coalesced_install_patterns', 'mscorsvw.exe,link.exe,mt.exe', 1, 1
	-- select * from host_config_prop (nolock) where name = 'Coalesced Install Patterns' -- To see what they currently have

	-- When trying to determine if the ab exclusion works; you can use a variation of this one; which grabs the events you are trying to manage, and the process generating them
	-- 	-- Get total events by day and [PROCESS]
	--	select top 1000 getutcdate(), ReceivedTimestamp, Timestamp,* 
	--		from eventsgui(1033) e
	--		where e.ReceivedTimeStamp > dateadd(MINUTE, -5, getutcdate())
	--		 and event_subtype_id = 1005
	--		 and process in ('c:\program files\landesk\ldclient\policysync.exe','c:\program files (x86)\landesk\ldclient\policysync.exe')
	--		order by e.ReceivedTimeStamp desc


-- -----------------------------------------------------
-- FAQ - Force an agent re-sync
-- -----------------------------------------------------
	-- set refresh_flags = refresh_flags|1 where host_id = xx
	-- [ExpireHostSession]

-- -----------------------------------------------------
-- FAQ - Set priority
-- -----------------------------------------------------
	-- UPDATE dbo.hostmain SET refresh_flags = refresh_flags|1040 WHERE host_id=xx

-- -----------------------------------------------------
-- FAQ - Query AD
-- -----------------------------------------------------
	-- gpresult /user TestUser /r
	
-- -----------------------------------------------------
-- FAQ - Set CC3
-- -----------------------------------------------------
	-- UPDATE dbo.hostmain SET refresh_flags = refresh_flags|8, cc_level = x
	
	-- RefreshFlags_CacheConsistency		= 0x08,	 
	-- flag just tells server to push new CC level to agents
	-- from: HostStorage.h
	--enum RefreshFlags
	--{
	--	RefreshFlags_None					= 0x00,	// No request for agent resynch
	--	RefreshFlags_AllFiles				= 0x01,	// Complete resynch of agent NAB and installer table is requested
	--	RefreshFlags_Installers				= 0x02,	// Rescan of programs installed on the computer is requested
	--	RefreshFlags_Debug					= 0x04,	// Trigger Debug Log on Agent.
	--	RefreshFlags_CacheConsistency		= 0x08,	
	--	RefreshFlags_PriorityBoost  		= 0x10,	// Boost the priority of this agent over all others.
	--	RefreshFlags_ConfigList		  		= 0x20,	// Tell agent to refresh config list.
	--	RefreshFlags_ResolveDuplicates		= 0x40,
	--	RefreshFlags_DebugActions			= 0x80,	// Trigger Debug actions on Agent.
	--	RefreshFlags_DoAction					= 0x100,	// Trigger an action on Agent.
	--	RefreshFlags_Reboot						= 0x200,	// Trigger agent Reboot.
	--	RefreshFlags_PriorityBoostBlog  = 0x400,	// Prioritize this host when processing file backlog
	--	RefreshFlags_ResetToTemplate  = 0x800,	// Reset this machine inventory to the template
	--	RefreshFlags_ConfigListFromFile  = 0x1000,	// Tell agent to refresh config list from the file.
	--	RefreshFlags_CopyTemplateInventory  = 0x2000,	// Copy template inventory to this clone
	--	RefreshFlags_PriorityBoostPermanent  = 0x4000,	// Boost the priority of this agent over all others permanently (until it is de-prioritized)
	--};


-- -----------------------------------------------------
-- FAQ - Required permissions for SQL User to run analysis scripts
-- -----------------------------------------------------	
-- use master
-- go
-- grant view server state, ALTER TRACE  to [sql user or group here] 
-- go
-- use das
-- go
-- grant select, execute  to [sql user or group here] 


-- 1. Database  configuration						
-- SQL Server configuration					
-- Required DB Permissions
-- 	CREATE ANY DATABASE		GRANT to Parity Account
-- 	VIEW SERVER STATE		GRANT to Parity Account
-- 	VIEW ANY DEFINITION		GRANT to Parity Account
-- 	ALTER TRACE				GRANT to Parity Account
-- 	ALTER SERVER STATE		GRANT to Parity Account


-- To confirm:
-- sp_helprotect null, 'enter user here'
	
-- If this is an upgrade of a backup of a production server
-- 	DAS database must be backed up a day before the upgrade
-- 		stop Parity/Bit9 services before backup				
-- 		use SQL Server Management Studio tools to run backup				
-- Database server must run under Windows Server version 2008 or 2012 with all patches					


-- These are the main sources that SQL will see from the Bit9 installation
--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
-- Bit9 		Source						ApplicationName					NTUserName						LoginName				HostName			NTDomainName		ServerName	SessionLoginName
--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
-- Server		Bit9 Security Platform™		SYSTEM							NT AUTHORITY\SYSTEM				WIN-G8TB6Q6KQA0			NT AUTHORITY		WIN-G8TB6Q6KQA0		NT AUTHORITY\SYSTEM
-- Reporter		.Net SqlClient Data 		Provider						SYSTEM							NT AUTHORITY\SYSTEM		WIN-G8TB6Q6KQA0		NT AUTHORITY		WIN-G8TB6Q6KQA0	NT AUTHORITY\SYSTEM
-- Console		PHP							Administrator					WIN-G8TB6Q6KQA0\Administrator	WIN-G8TB6Q6KQA0			WIN-G8TB6Q6KQA0		WIN-G8TB6Q6KQA0		WIN-G8TB6Q6KQA0\Administrator

-- -----------------------------------------------------
-- Known - ProcessDailyStats - when table row size is larger than int
-- -----------------------------------------------------
-- CASE WHEN MAX(p.rows)>2147483647 THEN 2147483647 ELSE MAX(p.rows) END 

-- -----------------------------------------------------
-- FAQ - Things to look at prior to upgrading
-- -----------------------------------------------------	
-- 	-- Duplicate Hashes
-- 	;with cte as ( 
-- 	SELECT a2.antibody_id as src_id, max(a1.antibody_id) as dest_id 
-- 		FROM dbo.antibodies a1 WITH (nolock) 
-- 		JOIN dbo.antibodies a2 WITH (nolock) ON a2.hash=a1.hash AND a2.hash_type=a1.hash_type AND a2.hash <> '' 
-- 		GROUP BY a1.hash, a2.antibody_id, a1.hash_type HAVING COUNT(a1.hash)>1 AND max(a1.antibody_id)<>a2.antibody_id 
-- 		) 
-- 	select count(1) AS 'Count of duplicate hashes' FROM CTE; 

-- 	-- Duplicate Deleted ABs
-- 	;with cte as ( 
-- 	SELECT max(antibody_instances_deleted_id) as id 
-- 		FROM dbo.antibody_instances_deleted WITH(nolock) 
-- 		GROUP BY host_id, pathname_id, filename_id HAVING count(*)>1 
-- 	) 
-- 	select count(1) 'Count of duplicate deleted abs' from cte; 

print 'analysis'
-- declare @HostCount int, @AvgEvents int, @AvgFileOps int
-- Average Events
print case 
	when @AvgEvents < 50 then 'Average Events [' + convert(varchar,@AvgEvents) + '] are normal'
	when @AvgEvents between 50 and 400 then 'Average Events [' + convert(varchar,@AvgEvents) + '] are higher than normal'
	else	
		'Average Events [' + convert(varchar,@AvgEvents) + '] are really high'
	end
	
print case 
	when @AvgFileOps < 500 then 'Average File Ops [' + convert(varchar,@AvgFileOps) + '] are normal'
	when @AvgFileOps between 500 and 1500 then 'Average File Ops [' + convert(varchar,@AvgFileOps) + '] are higher than normal'
	else	
		'Average File Ops [' + convert(varchar,@AvgFileOps) + '] are really high'
	end

	
select GetDate() as 'End Time'
print 'Second GetNextCertificateBatchToValidate'
exec GetNextCertificateBatchToValidate;

IF OBJECT_ID('tempdb..#TempEvents') IS NOT NULL DROP TABLE #TempEvents
