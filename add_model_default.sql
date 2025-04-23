-- Add default for forums.forum
INSERT INTO rbac_rbacmodeldefault (app, model, default_behaviour)
SELECT 'forums', 'forum', 'Allow'
WHERE NOT EXISTS (
    SELECT 1 FROM rbac_rbacmodeldefault 
    WHERE app = 'forums' AND model = 'forum'
);

-- Add defaults for other common models
INSERT INTO rbac_rbacmodeldefault (app, model, default_behaviour)
SELECT 'organisations', 'organisation', 'Allow'
WHERE NOT EXISTS (
    SELECT 1 FROM rbac_rbacmodeldefault 
    WHERE app = 'organisations' AND model = 'organisation'
);

INSERT INTO rbac_rbacmodeldefault (app, model, default_behaviour)
SELECT 'events', 'congress', 'Allow'
WHERE NOT EXISTS (
    SELECT 1 FROM rbac_rbacmodeldefault 
    WHERE app = 'events' AND model = 'congress'
);

INSERT INTO rbac_rbacmodeldefault (app, model, default_behaviour)
SELECT 'club_sessions', 'session', 'Allow'
WHERE NOT EXISTS (
    SELECT 1 FROM rbac_rbacmodeldefault 
    WHERE app = 'club_sessions' AND model = 'session'
);

INSERT INTO rbac_rbacmodeldefault (app, model, default_behaviour)
SELECT 'accounts', 'user', 'Allow'
WHERE NOT EXISTS (
    SELECT 1 FROM rbac_rbacmodeldefault 
    WHERE app = 'accounts' AND model = 'user'
);

INSERT INTO rbac_rbacmodeldefault (app, model, default_behaviour)
SELECT 'notifications', 'notification', 'Allow'
WHERE NOT EXISTS (
    SELECT 1 FROM rbac_rbacmodeldefault 
    WHERE app = 'notifications' AND model = 'notification'
);

-- It looks like there is no default set up for app=support model=helpdesk
INSERT INTO rbac_rbacmodeldefault (app, model, default_behaviour)
SELECT 'support', 'helpdesk', 'Allow'
WHERE NOT EXISTS (
    SELECT 1 FROM rbac_rbacmodeldefault 
    WHERE app = 'support' AND model = 'helpdesk'
);

-- It looks like there is no default set up for app=forums model=admin
INSERT INTO rbac_rbacmodeldefault (app, model, default_behaviour)
SELECT 'forums', 'admin', 'Allow'
WHERE NOT EXISTS (
    SELECT 1 FROM rbac_rbacmodeldefault 
    WHERE app = 'forums' AND model = 'admin'
);

-- It looks like there is no default set up for app=notifications model=realtime_send
INSERT INTO rbac_rbacmodeldefault (app, model, default_behaviour)
SELECT 'notifications', 'realtime_send', 'Allow'
WHERE NOT EXISTS (
    SELECT 1 FROM rbac_rbacmodeldefault 
    WHERE app = 'notifications' AND model = 'realtime_send'
);

-- It looks like there is no default set up for app=events model=global
INSERT INTO rbac_rbacmodeldefault (app, model, default_behaviour)
SELECT 'events', 'global', 'Allow'
WHERE NOT EXISTS (
    SELECT 1 FROM rbac_rbacmodeldefault 
    WHERE app = 'events' AND model = 'global'
);

-- It looks like there is no default set up for app=orgs model=admin
INSERT INTO rbac_rbacmodeldefault (app, model, default_behaviour)
SELECT 'orgs', 'admin', 'Allow'
WHERE NOT EXISTS (
    SELECT 1 FROM rbac_rbacmodeldefault 
    WHERE app = 'orgs' AND model = 'admin'
);

-- setup app
-- python manage.py add_superadmin
-- python manage.py add_rbac_static_global
-- python manage.py add_rbac_static_notifications